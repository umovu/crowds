"""
sa_context — current South African grounding, refreshed from live web search.

The hardcoded SA narrative ("load-shedding destroying small businesses") went
stale: agents kept raising a 2022-23 crisis as if it were current. This detects
what is ACTUALLY salient now via a web-search check and distils the real
snippets (the LLM SUMMARISES retrieved text — it never authors facts) into a
short, dated "current realities" block.

Cost is bounded: cached once per day (one batch of searches + one small
summarise call), shared across all sims via the data volume, so the per-run COGS
impact is effectively zero. Fails safe — returns None if search/LLM are
unavailable or disabled, and the caller falls back to the (softened) static
block. Disable entirely with SA_CONTEXT_DYNAMIC=0.
"""

import json
import os
import time
from datetime import datetime
from typing import List, Optional

from ..config import Config
from ..utils.logger import get_logger
from .serper_service import SerperService

logger = get_logger("fub.sa_context")

_CACHE_TTL_HOURS = float(os.environ.get("SA_CONTEXT_TTL_HOURS", "24"))


def _enabled() -> bool:
    return os.environ.get("SA_CONTEXT_DYNAMIC", "1").lower() not in ("0", "false", "no")


def _cache_path() -> str:
    return os.path.join(Config.DATA_ROOT, "cache", "sa_context.json")


def _read_cache() -> Optional[str]:
    try:
        with open(_cache_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        if time.time() - float(d.get("ts", 0)) < _CACHE_TTL_HOURS * 3600:
            return d.get("block") or None
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return None


def _write_cache(block: str) -> None:
    try:
        os.makedirs(os.path.dirname(_cache_path()), exist_ok=True)
        with open(_cache_path(), "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "block": block}, f)
    except OSError as e:
        logger.warning("Could not cache SA context: %s", e)


def _gather_snippets() -> List[str]:
    """Pull real search snippets on what is currently pressing in SA."""
    serper = SerperService()
    if not serper.is_available():
        return []
    when = datetime.now().strftime("%B %Y")
    queries = [
        f"most pressing issues facing ordinary South Africans {when}",
        f"is load shedding still a problem in South Africa {when}",
        f"South Africa cost of living unemployment crime {when}",
    ]
    snippets: List[str] = []
    for q in queries:
        res = serper.search(q, num_results=6)
        if not res.get("success"):
            continue
        for item in res.get("results", []):
            sn = (item.get("snippet") or item.get("title") or "").strip()
            if sn:
                snippets.append(sn)
    return snippets[:30]


def _distil(snippets: List[str]) -> Optional[str]:
    """Summarise the snippets into 6-8 current-reality bullets, grounded ONLY in
    the retrieved text (no LLM-authored facts). Returns None on any failure."""
    if not snippets:
        return None
    key = Config.LLM_API_KEY
    model = Config.LLM_MODEL_NAME
    if not (key and model):
        return None
    today = datetime.now().strftime("%d %B %Y")
    joined = "\n".join(f"- {s}" for s in snippets)
    system = (
        "You distil real web-search snippets into a short list of CURRENT realities "
        "facing ordinary South Africans, to ground a simulation. STRICT RULES: use "
        "ONLY what the snippets support; never add facts not present in them; if a "
        "past crisis (e.g. load-shedding) is described as eased or resolved, reflect "
        "that or omit it; include a number only if a snippet gives one. Output 6-8 "
        "short, plain present-tense bullet lines. No preamble, no closing line."
    )
    user = f"Today is {today}.\n\nSNIPPETS:\n{joined}\n\nCurrent realities (6-8 bullets):"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url=Config.LLM_BASE_URL or None)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            extra_body=Config.llm_extra_body() or None,
            max_tokens=500,
            temperature=0.2,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or None
    except Exception as e:
        logger.warning("SA context distil failed: %s", e)
        return None


def current_sa_realities() -> Optional[str]:
    """A dated 'current SA realities' block from live search, or None if
    unavailable/disabled. Cached ~daily and shared across sims; fails safe so the
    caller can fall back to the static block."""
    if not _enabled():
        return None
    cached = _read_cache()
    if cached is not None:
        return cached
    block = _distil(_gather_snippets())
    if not block:
        return None
    today = datetime.now().strftime("%d %B %Y")
    framed = (
        f"CURRENT SOUTH AFRICAN CONTEXT (verified by live web search, as of {today}) —\n"
        f"treat these as the up-to-date reality; do NOT assume a past crisis still\n"
        f"applies unless it appears below:\n{block}"
    )
    _write_cache(framed)
    logger.info("Refreshed current SA context from live search.")
    return framed
