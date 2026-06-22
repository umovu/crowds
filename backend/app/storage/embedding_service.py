"""
EmbeddingService — vector embeddings via local Ollama or a hosted API.

Local dev uses Ollama's /api/embed (nomic-embed-text, 768 dims). When
EMBEDDING_API_KEY is set (e.g. on Railway, with no Ollama), it switches to an
OpenAI-compatible /embeddings endpoint (DashScope/Jina/OpenAI), pinned to
EMBEDDING_DIMENSIONS so vectors stay compatible with existing storage.
"""

import time
import logging
from typing import List, Optional
from functools import lru_cache

import requests

from ..config import Config

logger = logging.getLogger('fub.embedding')


class EmbeddingService:
    """Generate embeddings using local Ollama server."""

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 30,
    ):
        self.model = model or Config.EMBEDDING_MODEL
        self.base_url = (base_url or Config.EMBEDDING_BASE_URL).rstrip('/')
        self.api_key = Config.EMBEDDING_API_KEY
        self.dimensions = Config.EMBEDDING_DIMENSIONS
        self.max_retries = max_retries
        self.timeout = timeout
        # With an API key → OpenAI-compatible hosted endpoint (DashScope/Jina/
        # OpenAI). Without → local Ollama. URLs/payloads differ between the two.
        self._openai_mode = bool(self.api_key)
        self._embed_url = (
            f"{self.base_url}/embeddings" if self._openai_mode
            else f"{self.base_url}/api/embed"
        )

        # Simple in-memory cache (text -> embedding vector)
        # Using dict instead of lru_cache because lists aren't hashable
        self._cache: dict[str, List[float]] = {}
        self._cache_max_size = 2000

    def embed(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text to embed

        Returns:
            768-dimensional float vector

        Raises:
            EmbeddingError: If Ollama request fails after retries
        """
        if not text or not text.strip():
            raise EmbeddingError("Cannot embed empty text")

        text = text.strip()

        # Check cache
        if text in self._cache:
            return self._cache[text]

        vectors = self._request_embeddings([text])
        vector = vectors[0]

        # Cache result
        self._cache_put(text, vector)

        return vector

    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Processes in batches to avoid overwhelming Ollama.

        Args:
            texts: List of input texts
            batch_size: Number of texts per request

        Returns:
            List of embedding vectors (same order as input)
        """
        if not texts:
            return []

        results: List[Optional[List[float]]] = [None] * len(texts)
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        # Check cache first
        for i, text in enumerate(texts):
            text = text.strip() if text else ""
            if text in self._cache:
                results[i] = self._cache[text]
            elif text:
                uncached_indices.append(i)
                uncached_texts.append(text)
            else:
                # Empty text — zero vector
                results[i] = [0.0] * self.dimensions

        # Batch-embed uncached texts
        if uncached_texts:
            all_vectors: List[List[float]] = []
            for start in range(0, len(uncached_texts), batch_size):
                batch = uncached_texts[start:start + batch_size]
                vectors = self._request_embeddings(batch)
                all_vectors.extend(vectors)

            # Place results and cache
            for idx, vec, text in zip(uncached_indices, all_vectors, uncached_texts):
                results[idx] = vec
                self._cache_put(text, vec)

        return results  # type: ignore

    def _request_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Make HTTP request to the embeddings endpoint with retry.

        Supports two backends, selected by whether an API key is configured:
          - OpenAI-compatible (DashScope/Jina/OpenAI): POST {base}/embeddings,
            response {"data": [{"embedding": [...], "index": i}, ...]}
          - Ollama: POST {base}/api/embed, response {"embeddings": [[...], ...]}

        Args:
            texts: List of texts to embed (both backends support batch)

        Returns:
            List of embedding vectors
        """
        headers = {}
        if self._openai_mode:
            headers["Authorization"] = f"Bearer {self.api_key}"
            payload = {
                "model": self.model,
                "input": texts,
                # Models that support it pin the vector size; harmless otherwise.
                "dimensions": self.dimensions,
            }
        else:
            payload = {
                "model": self.model,
                "input": texts,
            }

        provider = "Embedding API" if self._openai_mode else "Ollama"
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self._embed_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()

                if self._openai_mode:
                    items = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
                    embeddings = [item["embedding"] for item in items]
                else:
                    embeddings = data.get("embeddings", [])

                if len(embeddings) != len(texts):
                    raise EmbeddingError(
                        f"Expected {len(texts)} embeddings, got {len(embeddings)}"
                    )

                return embeddings

            except requests.exceptions.ConnectionError as e:
                last_error = e
                logger.warning(
                    f"{provider} connection failed (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning(
                    f"{provider} request timed out (attempt {attempt + 1}/{self.max_retries})"
                )
            except requests.exceptions.HTTPError as e:
                last_error = e
                logger.error(f"{provider} HTTP error: {e.response.status_code} - {e.response.text}")
                if e.response.status_code >= 500:
                    # Server error — retry
                    pass
                else:
                    # Client error (4xx) — don't retry
                    raise EmbeddingError(f"{provider} embedding failed: {e}") from e
            except (KeyError, ValueError) as e:
                raise EmbeddingError(f"Invalid {provider} response: {e}") from e

            # Exponential backoff
            if attempt < self.max_retries - 1:
                wait = 2 ** attempt
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)

        raise EmbeddingError(
            f"{provider} embedding failed after {self.max_retries} retries: {last_error}"
        )

    def _cache_put(self, text: str, vector: List[float]) -> None:
        """Add to cache, evicting oldest entries if full."""
        if len(self._cache) >= self._cache_max_size:
            # Remove ~10% of oldest entries
            keys_to_remove = list(self._cache.keys())[:self._cache_max_size // 10]
            for key in keys_to_remove:
                del self._cache[key]
        self._cache[text] = vector

    def health_check(self) -> bool:
        """Check if Ollama embedding endpoint is reachable."""
        try:
            vec = self.embed("health check")
            return len(vec) > 0
        except Exception:
            return False


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""
    pass
