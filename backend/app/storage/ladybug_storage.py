"""
LadybugStorage — LadybugDB implementation of GraphStorage.

LadybugDB is an embedded graph database (formerly LadybugDB).
- No server / Docker needed
- Native Cypher support
- Columnar storage optimized for analytical workloads
- Data persists to disk automatically
- Actively maintained successor to LadybugDB

Usage:
    storage = LadybugStorage()          # in-memory
    storage = LadybugStorage("./data")  # persistent
"""

import base64
import json
import os
import uuid
import logging
import shutil
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable

from ..config import Config
from .graph_storage import GraphStorage
from .embedding_service import EmbeddingService
from .ner_extractor import NERExtractor
from .search_service import SearchService

logger = logging.getLogger('fub.ladybug_storage')

# Lazy import so the module loads even when ladybug isn't installed
_ladybug = None


def _import_ladybug():
    global _ladybug
    if _ladybug is None:
        import ladybug
        _ladybug = ladybug
    return _ladybug


class LadybugStorage(GraphStorage):
    """LadybugDB implementation of the GraphStorage interface."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        embedding_service: Optional[EmbeddingService] = None,
        ner_extractor: Optional[NERExtractor] = None,
    ):
        ladybug = _import_ladybug()

        # Default to a project-local directory if no path given
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(__file__),
                "../../ladybug_data"
            )

        self._db_path = db_path
        # Ladybug creates the directory itself; pre-creating it can cause
        # "Database path cannot be a directory" on some versions.
        # Auto-recover from a corrupted WAL (the recurring failure mode here:
        # a force-killed backend leaves the WAL in an unreplayable state, so
        # the next startup throws "Corrupted wal file" and graph_storage stays
        # None — every graph build then 500s. Quarantine the bad files and
        # try again with a clean DB so the user is unblocked.)
        try:
            self._db = ladybug.Database(db_path)
        except Exception as e:
            msg = str(e)
            is_corrupt_wal = any(s in msg for s in (
                "Corrupted wal", "WAL record", "wal file",
            ))
            if not is_corrupt_wal:
                raise
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            logger.warning(
                "LadybugDB corrupted WAL detected — quarantining and "
                f"creating a fresh DB. Original error: {msg}"
            )
            for candidate in (db_path, f"{db_path}.wal", f"{db_path}.meta.json"):
                if os.path.exists(candidate):
                    try:
                        os.replace(candidate, f"{candidate}.corrupt-{ts}.bak")
                        logger.warning(f"  quarantined: {os.path.basename(candidate)} → .corrupt-{ts}.bak")
                    except OSError as move_err:
                        logger.error(f"  failed to quarantine {candidate}: {move_err}")
            # Retry with a clean slate. Any second failure is unrecoverable.
            self._db = ladybug.Database(db_path)
        self._conn = ladybug.Connection(self._db)

        self._embedding = embedding_service or EmbeddingService()
        self._ner = ner_extractor or NERExtractor()
        self._search = SearchService(self._embedding)

        # Graph metadata + ontology persist to a JSON sidecar next to the DB file,
        # since LadybugDB has no Graph node table. Without this, all graph→ontology
        # mappings are lost on restart and NER extraction runs with no entity types.
        self._meta_path = f"{db_path}.meta.json"
        self._graphs: Dict[str, Dict[str, Any]] = {}
        self._ontologies: Dict[str, Dict[str, Any]] = {}
        self._load_meta()

        # Ensure schema exists
        self._ensure_schema()

        logger.info(
            f"LadybugStorage initialized (path={db_path}, "
            f"{len(self._graphs)} graphs, {len(self._ontologies)} ontologies loaded)"
        )

    # ------------------------------------------------------------------
    # Metadata persistence (graphs + ontologies sidecar)
    # ------------------------------------------------------------------

    def _load_meta(self):
        """Load persisted graph metadata + ontologies from the JSON sidecar."""
        try:
            if os.path.exists(self._meta_path):
                with open(self._meta_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._graphs = data.get("graphs", {})
                self._ontologies = data.get("ontologies", {})
        except Exception as e:
            logger.warning(f"Failed to load Ladybug meta sidecar: {e}")
            self._graphs = {}
            self._ontologies = {}

    def _save_meta(self):
        """Persist graph metadata + ontologies to the JSON sidecar."""
        try:
            tmp = f"{self._meta_path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    {"graphs": self._graphs, "ontologies": self._ontologies},
                    f, ensure_ascii=False,
                )
            os.replace(tmp, self._meta_path)
        except Exception as e:
            logger.warning(f"Failed to save Ladybug meta sidecar: {e}")

    # ------------------------------------------------------------------
    # Schema setup
    # ------------------------------------------------------------------

    def _ensure_schema(self):
        """Create node / relationship tables if they don't exist."""
        # Ladybug requires tables to be created explicitly before use.
        # We use a single Entity node table and a single RELATION rel table.
        # Entity type labels are stored as a property instead of separate tables
        # (Ladybug doesn't support dynamic labels like Neo4j).
        try:
            self._conn.execute("""
                CREATE NODE TABLE IF NOT EXISTS Entity(
                    uuid STRING PRIMARY KEY,
                    graph_id STRING,
                    name STRING,
                    name_lower STRING,
                    labels STRING,
                    summary STRING,
                    attributes_json STRING,
                    embedding STRING,
                    created_at STRING
                )
            """)
        except Exception as e:
            # Table may already exist — safe to ignore
            logger.debug(f"Entity table creation note: {e}")

        try:
            self._conn.execute("""
                CREATE REL TABLE IF NOT EXISTS RELATION(
                    FROM Entity TO Entity,
                    uuid STRING,
                    graph_id STRING,
                    name STRING,
                    fact STRING,
                    fact_embedding STRING,
                    attributes_json STRING,
                    episode_ids STRING,
                    created_at STRING,
                    valid_at STRING,
                    invalid_at STRING,
                    expired_at STRING
                )
            """)
        except Exception as e:
            logger.debug(f"RELATION table creation note: {e}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run_query(self, query: str, params: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Execute a Cypher query and return results as a list of dicts."""
        prepared = self._conn.prepare(query)
        result = self._conn.execute(prepared, params or {})

        def _normalize_col(name: str) -> str:
            """Strip Ladybug variable prefixes like n.uuid -> uuid."""
            # Handles: n.name, r.fact, src.uuid, tgt.uuid, etc.
            if "." in name and not name.startswith("_"):
                return name.split(".", 1)[1]
            return name

        rows = []
        while result.has_next():
            row = result.get_next()
            # Ladybug returns a flat list per row — map to column names
            if hasattr(result, "get_column_names"):
                raw_names = result.get_column_names()
                names = [_normalize_col(n) for n in raw_names]
                rows.append({names[i]: row[i] for i in range(len(row))})
            else:
                rows.append({"_col_{i}": v for i, v in enumerate(row)})
        return rows

    # --- JSON packing for STRING columns -------------------------------
    # KuzuDB (LadybugDB) auto-parses JSON-looking string parameters into native
    # LIST/STRUCT and re-serializes them WITHOUT quotes on read, e.g.
    #   '["GangLeader"]'        -> '[GangLeader]'        (json.loads fails)
    #   '{"k": "v"}'            -> '{k: v}'              (json.loads fails)
    # To store JSON safely we base64-encode it — the output charset
    # ([A-Za-z0-9+/=]) contains no brackets/braces/quotes, so Kuzu leaves it
    # untouched. Reads tolerate both the new (base64) and any legacy formats.
    @staticmethod
    def _pack(obj: Any) -> str:
        raw = json.dumps(obj, ensure_ascii=False)
        return base64.b64encode(raw.encode("utf-8")).decode("ascii")

    @staticmethod
    def _unpack(s: str, default: Any):
        if not s:
            return default
        # New format: base64-encoded JSON
        try:
            decoded = base64.b64decode(s.encode("ascii")).decode("utf-8")
            return json.loads(decoded)
        except Exception:
            pass
        # Legacy / direct JSON (may be Kuzu-mangled — try, else default)
        try:
            return json.loads(s)
        except (json.JSONDecodeError, TypeError):
            return default

    @classmethod
    def _labels_to_str(cls, labels: List[str]) -> str:
        return cls._pack([l for l in labels if l and l != "Entity"])

    @classmethod
    def _labels_from_str(cls, s: str) -> List[str]:
        val = cls._unpack(s, [])
        return val if isinstance(val, list) else []

    @classmethod
    def _episode_ids_to_str(cls, episode_ids: List[str]) -> str:
        return cls._pack(episode_ids if isinstance(episode_ids, list) else [str(episode_ids)])

    @classmethod
    def _episode_ids_from_str(cls, s: str) -> List[str]:
        val = cls._unpack(s, [])
        if isinstance(val, list):
            return val
        return [str(val)] if val else []

    def _node_row_to_dict(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a Ladybug Entity row to the standard node dict."""
        attributes = self._unpack(row.get("attributes_json", ""), {})

        return {
            "uuid": row.get("uuid", ""),
            "name": row.get("name", ""),
            "labels": self._labels_from_str(row.get("labels", "")),
            "summary": row.get("summary", ""),
            "attributes": attributes,
            "created_at": row.get("created_at"),
        }

    def _edge_row_to_dict(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a Ladybug RELATION row to the standard edge dict."""
        attributes = self._unpack(row.get("attributes_json", ""), {})

        return {
            "uuid": row.get("uuid", ""),
            "name": row.get("name", ""),
            "fact": row.get("fact", ""),
            "source_node_uuid": row.get("src_uuid", ""),
            "target_node_uuid": row.get("tgt_uuid", ""),
            "attributes": attributes,
            "created_at": row.get("created_at"),
            "valid_at": row.get("valid_at"),
            "invalid_at": row.get("invalid_at"),
            "expired_at": row.get("expired_at"),
            "episode_ids": self._episode_ids_from_str(row.get("episode_ids", "")),
        }

    # ------------------------------------------------------------------
    # Graph lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Close Ladybug connection."""
        try:
            self._conn.close()
        except Exception:
            pass

    def create_graph(self, name: str, description: str = "") -> str:
        graph_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Ladybug doesn't have a Graph node table — we track in Python dict
        # and persist to the JSON sidecar so it survives restarts.
        self._graphs[graph_id] = {
            "graph_id": graph_id,
            "name": name,
            "description": description,
            "ontology_json": "{}",
            "created_at": now,
        }
        self._save_meta()

        logger.info(f"Created graph '{name}' with id {graph_id}")
        return graph_id

    def delete_graph(self, graph_id: str) -> None:
        # Delete all relations for this graph
        self._conn.execute(
            "MATCH (src:Entity)-[r:RELATION]->(tgt:Entity) "
            "WHERE r.graph_id = $gid DELETE r",
            {"gid": graph_id}
        )
        # Delete all entities for this graph
        self._conn.execute(
            "MATCH (n:Entity) WHERE n.graph_id = $gid DELETE n",
            {"gid": graph_id}
        )
        if graph_id in self._graphs:
            del self._graphs[graph_id]
        if graph_id in self._ontologies:
            del self._ontologies[graph_id]
        self._save_meta()
        logger.info(f"Deleted graph {graph_id}")

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        self._ontologies[graph_id] = ontology
        if graph_id in self._graphs:
            self._graphs[graph_id]["ontology_json"] = json.dumps(ontology, ensure_ascii=False)
        self._save_meta()

    def get_ontology(self, graph_id: str) -> Dict[str, Any]:
        # In-memory first, then fall back to the persisted graph row (survives restarts)
        if graph_id in self._ontologies:
            return self._ontologies[graph_id]
        g = self._graphs.get(graph_id)
        if g and g.get("ontology_json"):
            try:
                onto = json.loads(g["ontology_json"])
                if onto:
                    self._ontologies[graph_id] = onto  # repopulate cache
                    return onto
            except (json.JSONDecodeError, TypeError):
                pass
        return {}

    # ------------------------------------------------------------------
    # Add data (NER → nodes/edges)
    # ------------------------------------------------------------------

    def add_text(self, graph_id: str, text: str) -> str:
        """Process text: NER/RE → batch embed → create nodes/edges → return episode_id."""
        episode_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        ontology = self.get_ontology(graph_id)

        logger.info(f"[add_text] Starting NER extraction for chunk ({len(text)} chars)...")
        extraction = self._ner.extract(text, ontology)
        entities = extraction.get("entities", [])
        relations = extraction.get("relations", [])

        logger.info(
            f"[add_text] NER done: {len(entities)} entities, {len(relations)} relations"
        )

        # --- Batch embed all texts at once ---
        entity_summaries = [f"{e['name']} ({e['type']})" for e in entities]
        fact_texts = [r.get("fact", f"{r['source']} {r['type']} {r['target']}") for r in relations]
        all_texts_to_embed = entity_summaries + fact_texts

        all_embeddings: list = []
        if all_texts_to_embed:
            logger.info(f"[add_text] Batch-embedding {len(all_texts_to_embed)} texts...")
            try:
                all_embeddings = self._embedding.embed_batch(all_texts_to_embed)
            except Exception as e:
                logger.warning(f"[add_text] Batch embedding failed, falling back to empty: {e}")
                all_embeddings = [[] for _ in all_texts_to_embed]

        entity_embeddings = all_embeddings[:len(entities)]
        relation_embeddings = all_embeddings[len(entities):]
        logger.info(f"[add_text] Embedding done, writing to LadybugDB...")

        # MERGE entities (upsert by graph_id + lowercase name)
        entity_uuid_map: Dict[str, str] = {}
        for idx, entity in enumerate(entities):
            ename = entity["name"]
            etype = entity["type"]
            attrs = entity.get("attributes", {})
            summary_text = entity_summaries[idx]
            embedding = entity_embeddings[idx] if idx < len(entity_embeddings) else []
            e_uuid = str(uuid.uuid4())

            # Check if entity already exists
            existing = self._run_query(
                "MATCH (n:Entity) WHERE n.graph_id = $gid AND n.name_lower = $nl RETURN n.uuid AS uuid",
                {"gid": graph_id, "nl": ename.lower()},
            )
            if existing:
                actual_uuid = existing[0].get("uuid", e_uuid)
                # Update existing
                self._conn.execute(
                    "MATCH (n:Entity) WHERE n.uuid = $uuid "
                    "SET n.summary = CASE WHEN n.summary = '' THEN $summary ELSE n.summary END, "
                    "n.attributes_json = $attrs, n.embedding = $emb",
                    {
                        "uuid": actual_uuid,
                        "summary": summary_text,
                        "attrs": self._pack(attrs),
                        "emb": json.dumps(embedding),
                    },
                )
            else:
                actual_uuid = e_uuid
                self._conn.execute(
                    "CREATE (n:Entity {uuid: $uuid, graph_id: $gid, name: $name, "
                    "name_lower: $nl, labels: $labels, summary: $summary, "
                    "attributes_json: $attrs, embedding: $emb, created_at: $now})",
                    {
                        "uuid": actual_uuid,
                        "gid": graph_id,
                        "name": ename,
                        "nl": ename.lower(),
                        "labels": self._labels_to_str([etype] if etype and etype != "Entity" else []),
                        "summary": summary_text,
                        "attrs": self._pack(attrs),
                        "emb": json.dumps(embedding),
                        "now": now,
                    },
                )

            entity_uuid_map[ename.lower()] = actual_uuid

        # Create relations
        for idx, relation in enumerate(relations):
            source_name = relation["source"]
            target_name = relation["target"]
            rtype = relation["type"]
            fact = relation["fact"]

            source_uuid = entity_uuid_map.get(source_name.lower())
            target_uuid = entity_uuid_map.get(target_name.lower())

            if not source_uuid or not target_uuid:
                logger.warning(
                    f"Skipping relation {source_name}->{target_name}: "
                    f"entity not found in extraction results"
                )
                continue

            fact_embedding = relation_embeddings[idx] if idx < len(relation_embeddings) else []
            r_uuid = str(uuid.uuid4())

            self._conn.execute(
                "MATCH (src:Entity {uuid: $src_uuid}) "
                "MATCH (tgt:Entity {uuid: $tgt_uuid}) "
                "CREATE (src)-[:RELATION {uuid: $uuid, graph_id: $gid, name: $name, "
                "fact: $fact, fact_embedding: $fe, attributes_json: '{}', "
                "episode_ids: $eids, created_at: $now, valid_at: NULL, "
                "invalid_at: NULL, expired_at: NULL}]->(tgt)",
                {
                    "src_uuid": source_uuid,
                    "tgt_uuid": target_uuid,
                    "uuid": r_uuid,
                    "gid": graph_id,
                    "name": rtype,
                    "fact": fact,
                    "fe": json.dumps(fact_embedding),
                    "eids": self._episode_ids_to_str([episode_id]),
                    "now": now,
                },
            )

        logger.info(f"[add_text] Chunk done: episode={episode_id}")
        return episode_id

    def add_text_batch(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None,
    ) -> List[str]:
        """Batch-add text chunks with progress reporting."""
        episode_ids = []
        total = len(chunks)

        for i, chunk in enumerate(chunks):
            if not chunk or not chunk.strip():
                continue
            episode_id = self.add_text(graph_id, chunk)
            episode_ids.append(episode_id)

            if progress_callback:
                progress = (i + 1) / total
                progress_callback(progress)

            logger.info(f"Processed chunk {i + 1}/{total}")

        return episode_ids

    def wait_for_processing(
        self,
        episode_ids: List[str],
        progress_callback: Optional[Callable] = None,
        timeout: int = 600,
    ) -> None:
        """No-op — processing is synchronous in LadybugDB."""
        if progress_callback:
            progress_callback(1.0)

    # ------------------------------------------------------------------
    # Read nodes
    # ------------------------------------------------------------------

    def get_all_nodes(self, graph_id: str, limit: int = 2000) -> List[Dict[str, Any]]:
        rows = self._run_query(
            "MATCH (n:Entity) WHERE n.graph_id = $gid RETURN n.* ORDER BY n.created_at DESC LIMIT $limit",
            {"gid": graph_id, "limit": limit},
        )
        return [self._node_row_to_dict(r) for r in rows]

    def get_node(self, uuid: str) -> Optional[Dict[str, Any]]:
        rows = self._run_query(
            "MATCH (n:Entity) WHERE n.uuid = $uuid RETURN n.*",
            {"uuid": uuid},
        )
        if rows:
            return self._node_row_to_dict(rows[0])
        return None

    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        rows = self._run_query(
            "MATCH (src:Entity {uuid: $uuid})-[r:RELATION]->(tgt:Entity) "
            "RETURN r.*, src.uuid AS src_uuid, tgt.uuid AS tgt_uuid",
            {"uuid": node_uuid},
        )
        out = self._run_query(
            "MATCH (src:Entity)-[r:RELATION]->(tgt:Entity {uuid: $uuid}) "
            "RETURN r.*, src.uuid AS src_uuid, tgt.uuid AS tgt_uuid",
            {"uuid": node_uuid},
        )
        return [self._edge_row_to_dict(r) for r in rows + out]

    def get_nodes_by_label(self, graph_id: str, label: str) -> List[Dict[str, Any]]:
        # Ladybug doesn't support dynamic labels — we filter by labels property
        all_nodes = self.get_all_nodes(graph_id)
        return [n for n in all_nodes if label in n.get("labels", [])]

    # ------------------------------------------------------------------
    # Read edges
    # ------------------------------------------------------------------

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        rows = self._run_query(
            "MATCH (src:Entity)-[r:RELATION]->(tgt:Entity) "
            "WHERE r.graph_id = $gid "
            "RETURN r.*, src.uuid AS src_uuid, tgt.uuid AS tgt_uuid "
            "ORDER BY r.created_at DESC",
            {"gid": graph_id},
        )
        return [self._edge_row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
    ):
        """
        Keyword search over graph data.
        Returns dict with 'edges' and/or 'nodes' lists.
        """
        result = {"edges": [], "nodes": [], "query": query}
        query_lower = query.lower()

        if scope in ("nodes", "both"):
            nodes = self.get_all_nodes(graph_id)
            matching = [
                n for n in nodes
                if query_lower in n.get("name", "").lower()
                or query_lower in n.get("summary", "").lower()
            ][:limit]
            result["nodes"] = matching

        if scope in ("edges", "both"):
            edges = self.get_all_edges(graph_id)
            matching = [
                e for e in edges
                if query_lower in e.get("fact", "").lower()
                or query_lower in e.get("name", "").lower()
            ][:limit]
            result["edges"] = matching

        return result

    # ------------------------------------------------------------------
    # Graph info
    # ------------------------------------------------------------------

    def get_graph_info(self, graph_id: str) -> Dict[str, Any]:
        node_rows = self._run_query(
            "MATCH (n:Entity) WHERE n.graph_id = $gid RETURN count(n) AS cnt",
            {"gid": graph_id},
        )
        node_count = node_rows[0].get("cnt", 0) if node_rows else 0

        edge_rows = self._run_query(
            "MATCH (src:Entity)-[r:RELATION]->(tgt:Entity) "
            "WHERE r.graph_id = $gid RETURN count(r) AS cnt",
            {"gid": graph_id},
        )
        edge_count = edge_rows[0].get("cnt", 0) if edge_rows else 0

        # Distinct entity types from labels property
        nodes = self.get_all_nodes(graph_id)
        entity_types = set()
        for n in nodes:
            for label in n.get("labels", []):
                if label and label != "Entity":
                    entity_types.add(label)

        return {
            "graph_id": graph_id,
            "node_count": node_count,
            "edge_count": edge_count,
            "entity_types": list(entity_types),
        }

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        Full graph dump with enriched edge format (for frontend).
        """
        nodes = self.get_all_nodes(graph_id)
        edges = self.get_all_edges(graph_id)

        node_map: Dict[str, str] = {n["uuid"]: n["name"] for n in nodes}

        enriched_edges = []
        for edge in edges:
            ed = edge.copy()
            ed["fact_type"] = ed.get("name", "")
            ed["source_node_name"] = node_map.get(ed.get("source_node_uuid", ""), "")
            ed["target_node_name"] = node_map.get(ed.get("target_node_uuid", ""), "")
            ed["episodes"] = ed.get("episode_ids", [])
            enriched_edges.append(ed)

        return {
            "graph_id": graph_id,
            "nodes": nodes,
            "edges": enriched_edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }
