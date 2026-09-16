"""
Fub Simulation Storage Layer

Local graph storage replacing Zep Cloud:
- Neo4j CE for graph persistence (production)
- LadybugDB for fast embedded analytical graphs (recommended local)
- KGLite for lightweight in-memory graphs (dev-only)
- Ollama for embeddings (nomic-embed-text)
- LLM-based NER/RE extraction
- Hybrid search (vector + keyword)
"""

import logging

from .graph_storage import GraphStorage
from .neo4j_storage import Neo4jStorage
from .ladybug_storage import LadybugStorage
from .embedding_service import EmbeddingService, EmbeddingError
from .ner_extractor import NERExtractor
from .search_service import SearchService
from ..config import Config

logger = logging.getLogger('fub.storage')

#: The backends `get_storage` can build, in the order the API reports them.
BACKENDS = ("neo4j", "kglite", "ladybug")

__all__ = [
    "GraphStorage",
    "Neo4jStorage",
    "LadybugStorage",
    "EmbeddingService",
    "EmbeddingError",
    "NERExtractor",
    "SearchService",
    "BACKENDS",
    "get_storage",
    "close_storage",
]


def get_storage(backend: str = None) -> GraphStorage:
    """Factory function to get the appropriate storage backend."""
    backend = backend or Config.GRAPH_BACKEND

    if backend == "kglite":
        try:
            from .kglite_storage import KGLiteStorage
            return KGLiteStorage()
        except ImportError:
            raise RuntimeError("kglite package not installed. Run: pip install kglite")
    elif backend == "ladybug":
        return LadybugStorage()
    else:
        return Neo4jStorage()


def close_storage(storage) -> None:
    """Close a storage backend, ignoring a dirty close.

    Called before opening a different backend: the embedded ones (LadybugDB, KGLite)
    hold file locks, so the old instance has to let go first. A close that throws is
    logged and swallowed — it must not block the switch.
    """
    if storage is None or not hasattr(storage, 'close'):
        return
    try:
        storage.close()
    except Exception as e:  # noqa: BLE001 - a dirty close must not block the switch
        logger.warning(f"Failed to close old storage cleanly: {e}")
