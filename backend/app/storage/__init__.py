"""
Fub Simulation Storage Layer

Local graph storage replacing Zep Cloud:
- Neo4j CE for graph persistence
- KGLite for lightweight embedded graphs
- Ollama for embeddings (nomic-embed-text)
- LLM-based NER/RE extraction
- Hybrid search (vector + keyword)
"""

from .graph_storage import GraphStorage
from .neo4j_storage import Neo4jStorage
from .kglite_storage import KGLiteStorage
from .embedding_service import EmbeddingService, EmbeddingError
from .ner_extractor import NERExtractor
from .search_service import SearchService
from ..config import Config

__all__ = [
    "GraphStorage",
    "Neo4jStorage",
    "KGLiteStorage",
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
        return KGLiteStorage()
    else:
        return Neo4jStorage()
