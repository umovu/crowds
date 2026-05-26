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

from .graph_storage import GraphStorage
from .neo4j_storage import Neo4jStorage
from .ladybug_storage import LadybugStorage
from .embedding_service import EmbeddingService, EmbeddingError
from .ner_extractor import NERExtractor
from .search_service import SearchService
from ..config import Config

__all__ = [
    "GraphStorage",
    "Neo4jStorage",
    "LadybugStorage",
    "EmbeddingService",
    "EmbeddingError",
    "NERExtractor",
    "SearchService",
    "get_storage",
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
