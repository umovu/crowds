"""
OllamaEmbedding — wraps Ollama's nomic-embed-text for agentsociety's VectorStore.

agentsociety's VectorStore expects fastembed.SparseTextEmbedding — an object
whose embed() and query_embed() methods return objects with .indices and .values
as numpy arrays (Qdrant SparseVector format).

Ollama produces dense float vectors. We convert them to a pseudo-sparse format
by retaining the top-K dimensions by absolute magnitude. This preserves semantic
similarity while satisfying the interface agentsociety requires.

AgentToolbox is constructed with model_construct() to bypass Pydantic's
isinstance check on the embedding field.
"""

import numpy as np
import requests
from typing import Iterator

from ..utils.logger import get_logger

logger = get_logger("fub.ollama_embedding")

# Number of dimensions to keep when converting dense → sparse
# nomic-embed-text produces 768-dim vectors; keeping 256 is a good trade-off
TOP_K_SPARSE = 256


class SparseEmbeddingResult:
    """
    Mimics the result object fastembed.SparseTextEmbedding returns.
    VectorStore calls result.indices.tolist() and result.values.tolist().
    """

    def __init__(self, dense_vector: list):
        arr = np.array(dense_vector, dtype=np.float32)
        # Keep top-K dimensions by absolute magnitude
        top_idx = np.argsort(np.abs(arr))[-TOP_K_SPARSE:]
        top_idx = np.sort(top_idx)          # Qdrant requires sorted indices
        self.indices = top_idx              # numpy array — VectorStore calls .tolist()
        self.values  = arr[top_idx]         # numpy array — VectorStore calls .tolist()


class OllamaEmbedding:
    """
    Synchronous Ollama embedding client matching agentsociety's embedding interface.

    VectorStore calls:
        embed(documents: list[str])  → Iterator[SparseEmbeddingResult]
        query_embed(query: str)      → Iterator[SparseEmbeddingResult]
    """

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        timeout: int = 30,
    ):
        self.model    = model
        self.base_url = base_url.rstrip("/")
        self.timeout  = timeout
        self._endpoint = f"{self.base_url}/api/embeddings"

    def _embed_one(self, text: str) -> SparseEmbeddingResult:
        try:
            resp = requests.post(
                self._endpoint,
                json={"model": self.model, "prompt": text},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            dense = resp.json()["embedding"]
            return SparseEmbeddingResult(dense)
        except Exception as e:
            logger.warning(f"Ollama embedding failed: {e} — using zero vector")
            # Return zero sparse vector so VectorStore doesn't crash
            result = SparseEmbeddingResult([0.0] * 768)
            return result

    def embed(self, documents: list) -> Iterator[SparseEmbeddingResult]:
        """Batch embed — called by VectorStore.add_documents()."""
        for doc in documents:
            yield self._embed_one(str(doc))

    def query_embed(self, query: str) -> Iterator[SparseEmbeddingResult]:
        """Single query embed — called by VectorStore.similarity_search()."""
        yield self._embed_one(str(query))

    def health_check(self) -> bool:
        """Returns True if Ollama is reachable and the model is available."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            models = [m["name"].split(":")[0] for m in resp.json().get("models", [])]
            return self.model.split(":")[0] in models
        except Exception:
            return False
