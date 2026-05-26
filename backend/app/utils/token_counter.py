"""
TokenCounter — count tokens in prompts / completions and estimate API cost.

Uses tiktoken for fast local counting.  For models not in tiktoken's registry
(deepseek-chat, ollama/…, etc.) we fall back to the ``cl100k_base`` encoder,
which is accurate to within ~5 % for most modern BPE tokenizers.

Example
-------
    from app.utils.token_counter import TokenCounter

    tc = TokenCounter(model_name="deepseek-chat")
    prompt_toks = tc.count_messages(messages)
    completion_toks = tc.count_text(response_text)
    cost = tc.estimate_cost(prompt_toks, completion_toks)
"""

import json
import logging
import os
from typing import Dict, List, Optional, Tuple

import tiktoken

logger = logging.getLogger("fub.token_counter")

# ------------------------------------------------------------------
# Pricing table (USD per 1 000 000 tokens)
# Override via env vars: LLM_PRICE_PROMPT_PER_1M, LLM_PRICE_COMPLETION_PER_1M
# ------------------------------------------------------------------
_DEFAULT_PRICING: Dict[str, Tuple[float, float]] = {
    # OpenAI
    "gpt-4o":            (2.50,   10.00),
    "gpt-4o-mini":       (0.15,    0.60),
    "gpt-4-turbo":       (10.00,   30.00),
    "gpt-4":             (30.00,   60.00),
    "gpt-3.5-turbo":     (0.50,    1.50),
    # Qwen (Alibaba DashScope international — USD per 1M tokens, 2026)
    "qwen3.6-plus":      (0.325,   1.95),
    "qwen3.6-flash":     (0.25,    1.50),
    "qwen3.5-plus":      (0.30,    1.80),
    # DeepSeek (cache-miss pricing — update at https://platform.deepseek.com/api-docs/quick_start/pricing)
    "deepseek-chat":     (0.14,    0.28),
    "deepseek-coder":    (0.14,    0.28),
    "deepseek-reasoner": (0.55,    2.19),
    "deepseek-v4-flash": (0.10,    0.30),   # approximate — verify with DeepSeek
    "deepseek-v4-pro":   (0.50,    2.00),   # approximate — verify with DeepSeek
    # Groq-hosted models (https://groq.com/pricing)
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant":    (0.05, 0.08),
    "llama-3.2-1b-preview":    (0.04, 0.04),
    "llama-3.2-3b-preview":    (0.06, 0.06),
    "llama-3.2-11b-vision-preview": (0.18, 0.18),
    "llama-3.2-90b-vision-preview": (0.90, 0.90),
    "mixtral-8x7b-32768":      (0.24, 0.24),
    "gemma-7b-it":             (0.10, 0.10),
    # Ollama (local — $0)
    "mistral":           (0.0, 0.0),
    "llama2":            (0.0, 0.0),
    "llama3":            (0.0, 0.0),
}


def _get_pricing(model_name: str) -> Tuple[float, float]:
    """Return (prompt_price_per_1m, completion_price_per_1m)."""
    # Allow global override via env
    env_prompt = os.environ.get("LLM_PRICE_PROMPT_PER_1M")
    env_completion = os.environ.get("LLM_PRICE_COMPLETION_PER_1M")
    if env_prompt is not None and env_completion is not None:
        try:
            return (float(env_prompt), float(env_completion))
        except ValueError:
            pass

    # Strip common prefixes (groq/, ollama/, etc.)
    clean = model_name.lower()
    for prefix in ("groq/", "ollama/", "openai/"):
        if clean.startswith(prefix):
            clean = clean[len(prefix):]

    # Exact match
    if clean in _DEFAULT_PRICING:
        return _DEFAULT_PRICING[clean]

    # Fuzzy match on base model name
    for key, price in _DEFAULT_PRICING.items():
        if key in clean or clean in key:
            return price

    # Default fallback (cheap local model assumption)
    logger.warning(f"No pricing found for '{model_name}' — assuming $0.  Set LLM_PRICE_PROMPT_PER_1M and LLM_PRICE_COMPLETION_PER_1M to override.")
    return (0.0, 0.0)


class TokenCounter:
    """
    Count tokens and estimate cost for a given model.

    Parameters
    ----------
    model_name : str, optional
        The model identifier (e.g. ``deepseek-chat``, ``gpt-4o``).
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or os.environ.get("LLM_MODEL_NAME", "unknown")
        self._encoding = self._get_encoding(self.model_name)
        self._prompt_price_1m, self._completion_price_1m = _get_pricing(self.model_name)

    # ------------------------------------------------------------------
    # Encoding
    # ------------------------------------------------------------------

    @staticmethod
    def _get_encoding(model_name: str):
        """Return a tiktoken Encoding.  Falls back to cl100k_base."""
        clean = model_name.lower()
        # Strip provider prefixes
        for prefix in ("groq/", "ollama/", "openai/"):
            if clean.startswith(prefix):
                clean = clean[len(prefix):]

        # Map common model names to tiktoken encodings
        encoding_name = "cl100k_base"  # safe default
        if clean.startswith("gpt-4") or clean.startswith("gpt-3.5"):
            try:
                return tiktoken.encoding_for_model(clean)
            except KeyError:
                encoding_name = "cl100k_base"
        elif clean.startswith("text-embedding"):
            encoding_name = "cl100k_base"
        # DeepSeek, Mistral, Llama, etc. all use byte-pair schemes that are
        # *very* close to cl100k_base in token count (< 5 % error).
        try:
            return tiktoken.get_encoding(encoding_name)
        except Exception:
            # Should never happen — cl100k_base ships with tiktoken
            return tiktoken.get_encoding("cl100k_base")

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    def count_text(self, text: str) -> int:
        """Count tokens in a plain string."""
        if not text:
            return 0
        return len(self._encoding.encode(text))

    def count_messages(self, messages: List[Dict[str, str]]) -> int:
        """
        Count tokens in an OpenAI-style message list.

        Implements the standard chat-format counting heuristic:
        https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
        """
        if not messages:
            return 0

        num_tokens = 0
        tokens_per_message = 3
        tokens_per_name = 1

        for message in messages:
            num_tokens += tokens_per_message
            for key, value in message.items():
                if value is None:
                    continue
                num_tokens += len(self._encoding.encode(str(value)))
                if key == "name":
                    num_tokens += tokens_per_name

        # Every reply is primed with <|start|>assistant<|message|>
        num_tokens += 3
        return num_tokens

    # ------------------------------------------------------------------
    # Cost estimation
    # ------------------------------------------------------------------

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Return estimated cost in USD."""
        prompt_cost = (prompt_tokens / 1_000_000) * self._prompt_price_1m
        completion_cost = (completion_tokens / 1_000_000) * self._completion_price_1m
        return round(prompt_cost + completion_cost, 6)

    def get_pricing_info(self) -> Dict[str, float]:
        """Return pricing breakdown."""
        return {
            "model": self.model_name,
            "prompt_price_per_1m_usd": self._prompt_price_1m,
            "completion_price_per_1m_usd": self._completion_price_1m,
        }

    # ------------------------------------------------------------------
    # Batch / convenience
    # ------------------------------------------------------------------

    def count_and_estimate(
        self,
        messages: List[Dict[str, str]],
        completion_text: str,
    ) -> Dict[str, any]:
        """One-shot count + estimate."""
        prompt_tokens = self.count_messages(messages)
        completion_tokens = self.count_text(completion_text)
        cost = self.estimate_cost(prompt_tokens, completion_tokens)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "estimated_cost_usd": cost,
        }


# ------------------------------------------------------------------
# Singleton / module-level helpers for quick use
# ------------------------------------------------------------------

_default_counter: Optional[TokenCounter] = None


def get_default_counter() -> TokenCounter:
    global _default_counter
    if _default_counter is None:
        _default_counter = TokenCounter()
    return _default_counter


def quick_count(text: str) -> int:
    return get_default_counter().count_text(text)


def quick_count_messages(messages: List[Dict[str, str]]) -> int:
    return get_default_counter().count_messages(messages)


def quick_estimate(prompt_tokens: int, completion_tokens: int) -> float:
    return get_default_counter().estimate_cost(prompt_tokens, completion_tokens)
