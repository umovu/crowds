"""
KGLiteStorage — KGLite implementation of GraphStorage.

A lightweight, embedded graph database that requires no server setup.
Uses pandas DataFrames for node/edge storage with in-memory fallback dicts.
"""

import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable

import pandas as pd

from kglite import KnowledgeGraph

from ..config import Config
from .graph_storage import GraphStorage
from .embedding_service import EmbeddingService
from .ner_extractor import NERExtractor
from .search_service import SearchService

logger = logging.getLogger('fub.kglite_storage')


class KGLiteStorage(GraphStorage):
    """KGLite implementation of the GraphStorage interface."""

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        ner_extractor: Optional[NERExtractor] = None,
    ):
        self._graph = KnowledgeGraph()
        self._embedding = embedding_service or EmbeddingService()
        self._ner = ner_extractor or NERExtractor()
        self._search = SearchService(self._embedding)

        self._graphs: Dict[str, Dict[str, Any]] = {}
        self._entities: Dict[str, Dict[str, Any]] = {}
        self._relations: List[Dict[str, Any]] = []
        self._ontologies: Dict[str, Dict[str, Any]] = {}

        logger.info("KGLiteStorage initialized")

    def close(self):
        """Close the KGLite storage (no-op for in-memory)."""
        pass

    def _get_graph_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        return [e for e in self._entities.values() if e.get("graph_id") == graph_id]

    def _get_graph_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        return [r for r in self._relations if r.get("graph_id") == graph_id]

    def _get_or_create_entity(self, graph_id: str, name: str, name_lower: str,
                               entity_type: str, summary: str = "",
                               attributes: Dict = None, embedding: List = None) -> str:
        key = f"{graph_id}:{name_lower}"
        if key in self._entities:
            return self._entities[key]["uuid"]

        entity_uuid = str(uuid.uuid4())
        self._entities[key] = {
            "uuid": entity_uuid,
            "graph_id": graph_id,
            "name": name,
            "name_lower": name_lower,
            "labels": [entity_type] if entity_type and entity_type != "Entity" else [],
            "summary": summary,
            "attributes": attributes or {},
            "embedding": embedding or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Add to KGLite using DataFrame API
        try:
            df = pd.DataFrame([{
                "uuid": entity_uuid,
                "name": name,
                "summary": summary,
                "entity_type": entity_type or "Entity",
                "graph_id": graph_id,
            }])
            self._graph.add_nodes(df, node_type="Entity", unique_id_field="uuid")
        except Exception as e:
            logger.debug(f"KGLite node creation warning: {e}")

        return entity_uuid

    def _create_relation(self, graph_id: str, source_uuid: str, target_uuid: str,
                         relation_type: str, fact: str, episode_id: str) -> str:
        rel_uuid = str(uuid.uuid4())
        self._relations.append({
            "uuid": rel_uuid,
            "graph_id": graph_id,
            "name": relation_type,
            "fact": fact,
            "source_node_uuid": source_uuid,
            "target_node_uuid": target_uuid,
            "episode_ids": [episode_id],
            "attributes": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "valid_at": None,
            "invalid_at": None,
            "expired_at": None,
        })

        # Add to KGLite using connections API
        try:
            conn_df = pd.DataFrame([{
                "source": source_uuid,
                "target": target_uuid,
                "relation_type": relation_type,
                "fact": fact,
                "graph_id": graph_id,
            }])
            self._graph.add_connections(conn_df, source_id_field="source", target_id_field="target", edge_type_field="relation_type")
        except Exception as e:
            logger.debug(f"KGLite relation creation warning: {e}")

        return rel_uuid

    def create_graph(self, name: str, description: str = "") -> str:
        graph_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        self._graphs[graph_id] = {
            "graph_id": graph_id,
            "name": name,
            "description": description,
            "ontology_json": "{}",
            "created_at": now,
        }

        logger.info(f"Created graph '{name}' with id {graph_id}")
        return graph_id

    def delete_graph(self, graph_id: str) -> None:
        if graph_id in self._graphs:
            del self._graphs[graph_id]

        keys_to_delete = [k for k, v in self._entities.items() if v.get("graph_id") == graph_id]
        for key in keys_to_delete:
            del self._entities[key]

        self._relations = [r for r in self._relations if r.get("graph_id") != graph_id]

        if graph_id in self._ontologies:
            del self._ontologies[graph_id]

        logger.info(f"Deleted graph {graph_id}")

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        self._ontologies[graph_id] = ontology
        if graph_id in self._graphs:
            self._graphs[graph_id]["ontology_json"] = json.dumps(ontology, ensure_ascii=False)

    def get_ontology(self, graph_id: str) -> Dict[str, Any]:
        return self._ontologies.get(graph_id, {})

    def add_text(self, graph_id: str, text: str) -> str:
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
        logger.info(f"[add_text] Embedding done, writing to KGLite...")

        entity_uuid_map: Dict[str, str] = {}
        for idx, entity in enumerate(entities):
            ename = entity["name"]
            etype = entity["type"]
            attrs = entity.get("attributes", {})
            embedding = entity_embeddings[idx] if idx < len(entity_embeddings) else []
            summary = entity_summaries[idx]

            e_uuid = self._get_or_create_entity(
                graph_id, ename, ename.lower(), etype, summary, attrs, embedding
            )
            entity_uuid_map[ename.lower()] = e_uuid

        for idx, relation in enumerate(relations):
            source_name = relation["source"]
            target_name = relation["target"]
            rtype = relation["type"]
            fact = relation["fact"]

            source_uuid = entity_uuid_map.get(source_name.lower())
            target_uuid = entity_uuid_map.get(target_name.lower())

            if not source_uuid or not target_uuid:
                logger.warning(
                    f"Skipping relation {source_name}->{target_name}: entity not found"
                )
                continue

            self._create_relation(graph_id, source_uuid, target_uuid, rtype, fact, episode_id)

        logger.info(f"[add_text] Chunk done: episode={episode_id}")
        return episode_id

    def add_text_batch(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None,
    ) -> List[str]:
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
        if progress_callback:
            progress_callback(1.0)

    def get_all_nodes(self, graph_id: str, limit: int = 2000) -> List[Dict[str, Any]]:
        nodes = self._get_graph_nodes(graph_id)
        return nodes[:limit]

    def get_node(self, uuid: str) -> Optional[Dict[str, Any]]:
        for entity in self._entities.values():
            if entity["uuid"] == uuid:
                return entity
        return None

    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        edges = []
        for rel in self._relations:
            if rel.get("source_node_uuid") == node_uuid or rel.get("target_node_uuid") == node_uuid:
                edges.append(rel)
        return edges

    def get_nodes_by_label(self, graph_id: str, label: str) -> List[Dict[str, Any]]:
        nodes = self._get_graph_nodes(graph_id)
        return [n for n in nodes if label in n.get("labels", [])]

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        return self._get_graph_edges(graph_id)

    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
    ):
        result = {"edges": [], "nodes": [], "query": query}

        nodes = self._get_graph_nodes(graph_id)
        edges = self._get_graph_edges(graph_id)

        query_lower = query.lower()

        if scope in ("nodes", "both"):
            matching_nodes = [
                n for n in nodes
                if query_lower in n.get("name", "").lower() or
                   query_lower in n.get("summary", "").lower()
            ][:limit]
            result["nodes"] = matching_nodes

        if scope in ("edges", "both"):
            matching_edges = [
                e for e in edges
                if query_lower in e.get("fact", "").lower() or
                   query_lower in e.get("name", "").lower()
            ][:limit]
            result["edges"] = matching_edges

        return result

    def get_graph_info(self, graph_id: str) -> Dict[str, Any]:
        nodes = self._get_graph_nodes(graph_id)
        edges = self._get_graph_edges(graph_id)

        entity_types = set()
        for node in nodes:
            for label in node.get("labels", []):
                if label != "Entity":
                    entity_types.add(label)

        return {
            "graph_id": graph_id,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "entity_types": list(entity_types),
        }

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        nodes = self._get_graph_nodes(graph_id)
        edges = self._get_graph_edges(graph_id)

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
