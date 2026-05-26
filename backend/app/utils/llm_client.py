"""
LLM Client Wrapper
Unified OpenAI format API calls
Supports Ollama num_ctx parameter to prevent prompt truncation
"""

import json
import os
import re
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config
from .token_counter import TokenCounter


class LLMClient:
    """LLM Client with built-in token counting and cost estimation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 300.0
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME

        # Remove groq/ prefix if present (base_url already specifies Groq)
        if self.model and self.model.startswith('groq/'):
            self.model = self.model[5:]
            print(f"[LLMClient] Using Groq model: {self.model}")

        if not self.api_key:
            raise ValueError("LLM_API_KEY not configured")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
        )

        # Ollama context window size — prevents prompt truncation.
        # Read from env OLLAMA_NUM_CTX, default 8192 (Ollama default is only 2048).
        self._num_ctx = int(os.environ.get('OLLAMA_NUM_CTX', '8192'))

        # Token counting & cost estimation
        self._token_counter = TokenCounter(self.model)
        self._stats = {
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "estimated_cost_usd": 0.0,
        }

    def _is_ollama(self) -> bool:
        """Check if we're talking to an Ollama server."""
        return '11434' in (self.base_url or '')

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        Send chat request

        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Max token count
            response_format: Response format (e.g., JSON mode)

        Returns:
            Model response text
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            kwargs["response_format"] = response_format

        # For Ollama: pass num_ctx via extra_body to prevent prompt truncation
        if self._is_ollama() and self._num_ctx:
            kwargs["extra_body"] = {
                "options": {"num_ctx": self._num_ctx}
            }

        # Provider-specific extras (e.g. enable_thinking:false for Qwen)
        from ..config import Config
        extras = Config.llm_extra_body()
        if extras:
            kwargs.setdefault("extra_body", {}).update(extras)

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        # Some models (like MiniMax M2.5) include <think>thinking content in response, need to remove
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()

        # Record token usage (actual if provided, else estimated)
        usage = None
        if hasattr(response, "usage") and response.usage:
            try:
                usage = {
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                }
            except Exception:
                pass
        token_info = self._record_usage(messages, content, usage)
        # Log concise token info
        import logging
        logging.getLogger("fub.llm_client").debug(
            f"Tokens  prompt={token_info['prompt_tokens']}  "
            f"completion={token_info['completion_tokens']}  "
            f"cost=${token_info['estimated_cost_usd']:.6f}"
        )

        return content

    def _is_groq(self) -> bool:
        """Check if we're talking to a Groq server."""
        return 'groq' in (self.base_url or '').lower()

    # ------------------------------------------------------------------
    # Token counting & stats
    # ------------------------------------------------------------------

    def count_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Count prompt tokens for a message list."""
        return self._token_counter.count_messages(messages)

    def get_stats(self) -> Dict[str, Any]:
        """Return cumulative token usage and cost stats."""
        return dict(self._stats)

    def reset_stats(self):
        """Reset cumulative stats."""
        self._stats = {
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "estimated_cost_usd": 0.0,
        }

    def _record_usage(self, messages: List[Dict[str, str]], response_text: str,
                      usage: Optional[Dict[str, int]] = None):
        """Update internal stats after a chat call."""
        if usage:
            prompt_toks = usage.get("prompt_tokens", 0)
            completion_toks = usage.get("completion_tokens", 0)
        else:
            prompt_toks = self._token_counter.count_messages(messages)
            completion_toks = self._token_counter.count_text(response_text)

        cost = self._token_counter.estimate_cost(prompt_toks, completion_toks)

        self._stats["calls"] += 1
        self._stats["prompt_tokens"] += prompt_toks
        self._stats["completion_tokens"] += completion_toks
        self._stats["estimated_cost_usd"] = round(
            self._stats["estimated_cost_usd"] + cost, 6
        )

        return {
            "prompt_tokens": prompt_toks,
            "completion_tokens": completion_toks,
            "total_tokens": prompt_toks + completion_toks,
            "estimated_cost_usd": cost,
        }

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        Send chat request and return JSON

        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Max token count

        Returns:
            Parsed JSON object
        """
        processed_messages = messages
        if self._is_groq():
            processed_messages = []
            for msg in messages:
                if msg["role"] == "user" and "json" not in msg["content"].lower():
                    msg = dict(msg)
                    msg["content"] = msg["content"] + "\n\nPlease respond with valid JSON only."
                processed_messages.append(msg)

        # Build chat kwargs
        chat_kwargs = {
            "messages": processed_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        # Only add response_format for non-Groq APIs (not supported by Groq)
        if not self._is_groq():
            chat_kwargs["response_format"] = {"type": "json_object"}
        
        response = self.chat(**chat_kwargs)
        # Clean markdown code block markers
        cleaned_response = response.strip()
        cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response, flags=re.IGNORECASE)
        cleaned_response = re.sub(r'\n?```\s*$', '', cleaned_response)
        cleaned_response = cleaned_response.strip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON format from LLM: {cleaned_response}")
