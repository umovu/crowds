"""
DeepResearchService — iterative web research for SA archetype enrichment.

Implements the deep-research algorithm (generate queries → Firecrawl search+scrape →
extract learnings → follow-up queries → repeat) using firecrawl-py and openai,
both of which are already installed. No torch or sentence-transformers needed.

Activated when FIRECRAWL_API_KEY is set. Uses LLM_API_KEY / LLM_BASE_URL /
LLM_MODEL_NAME (your existing Groq config) automatically.
"""

import asyncio
import json
import os
from typing import Dict, List

from ..utils.logger import get_logger

logger = get_logger("fub.deep_research")


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def _is_available() -> bool:
    # Research can run if either Jina or Firecrawl is configured.
    # Jina is preferred (more generous free tier).
    return bool(
        os.environ.get("JINA_API_KEY")
        or os.environ.get("FIRECRAWL_API_KEY")
        or os.environ.get("FIRECRAWL_KEY")
    )


def _firecrawl_key() -> str:
    return os.environ.get("FIRECRAWL_API_KEY") or os.environ.get("FIRECRAWL_KEY", "")


def _llm_config() -> dict:
    return {
        "api_key": os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", "ollama"),
        "base_url": os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_API_BASE_URL", "http://localhost:11434/v1"),
        "model": os.environ.get("LLM_MODEL_NAME", "llama-3.3-70b-versatile"),
    }


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

async def _llm_json(prompt: str, system: str = "") -> dict:
    """Call the configured LLM and parse the response as JSON."""
    from openai import AsyncOpenAI
    cfg = _llm_config()
    client = AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        from ..config import Config
        kwargs = {
            "model": cfg["model"],
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1024,
        }
        extra = Config.llm_extra_body()
        if extra:
            kwargs["extra_body"] = extra
        resp = await client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content or ""
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as e:
        logger.warning(f"LLM JSON parse failed: {e}")
        return {}


async def _generate_queries(topic: str, parent_learnings: List[str], breadth: int) -> List[str]:
    """Generate search queries for a topic, informed by prior learnings."""
    context = ""
    if parent_learnings:
        context = "\n\nPrior findings (avoid repeating these):\n" + "\n".join(f"- {l}" for l in parent_learnings[:5])

    prompt = (
        f"Generate {breadth} specific web search queries to research the following topic about South Africa.\n"
        f"Topic: {topic}{context}\n\n"
        f'Return JSON: {{"queries": ["query1", "query2", ...]}}\n'
        f"Queries should be specific, varied, and focused on statistics, policy, lived experience."
    )
    result = await _llm_json(prompt, system="You are a research assistant. Return only valid JSON.")
    queries = result.get("queries", [])
    if not queries:
        return [topic]
    return queries[:breadth]


async def _extract_learnings(query: str, content: str, url: str) -> List[str]:
    """Extract key factual learnings from scraped page content."""
    if not content or len(content) < 100:
        return []
    prompt = (
        f"Extract up to 5 specific factual learnings from this web page relevant to: {query}\n\n"
        f"URL: {url}\nContent (first 3000 chars):\n{content[:3000]}\n\n"
        f'Return JSON: {{"learnings": ["learning1", "learning2", ...]}}\n'
        f"Each learning must be a specific fact, statistic, quote, or data point. No vague summaries."
    )
    result = await _llm_json(prompt, system="You are a research analyst. Return only valid JSON.")
    return result.get("learnings", [])


# ---------------------------------------------------------------------------
# Core deep research loop
# ---------------------------------------------------------------------------

async def _deep_research(
    query: str,
    breadth: int,
    depth: int,
    visited_urls: List[str],
    all_learnings: List[str],
) -> None:
    """Recursive research: generate queries → search → scrape → extract → repeat.

    Uses Jina (more generous free tier) when JINA_API_KEY is set;
    falls back to Firecrawl when not.
    """
    from .jina_service import JinaService
    jina = JinaService()
    use_jina = bool(jina.api_key)

    if not use_jina:
        from firecrawl import FirecrawlApp
        fc = FirecrawlApp(api_key=_firecrawl_key())

    queries = await _generate_queries(query, all_learnings, breadth)
    logger.info(f"Depth {depth} — {len(queries)} queries via {'Jina' if use_jina else 'Firecrawl'}: {queries}")

    for q in queries:
        items = []
        try:
            if use_jina:
                resp = jina.search_and_scrape(q, num_results=3)
                if resp.get("success"):
                    items = [
                        {"url": s.get("url"), "markdown": s.get("content", "")}
                        for s in resp.get("scraped_content", [])
                    ]
            else:
                result = fc.search(q, params={"limit": 3, "scrapeOptions": {"formats": ["markdown"]}})
                items = result.get("data", []) if isinstance(result, dict) else (result or [])
        except Exception as e:
            logger.warning(f"Search failed for '{q}': {e}")
            continue

        for item in items:
            url = item.get("url", "")
            if not url or url in visited_urls:
                continue
            visited_urls.append(url)

            content = item.get("markdown", "") or item.get("content", "") or item.get("description", "")
            learnings = await _extract_learnings(q, content, url)
            for l in learnings:
                if l not in all_learnings:
                    all_learnings.append(l)

    if depth > 1 and all_learnings:
        await _deep_research(query, max(1, breadth - 1), depth - 1, visited_urls, all_learnings)


async def _research_one(archetype: str, query: str, document_text: str, breadth: int, depth: int) -> tuple:
    """Run iterative deep research for a single archetype. Returns (archetype, text)."""
    focused = (
        f"Socio-economic conditions, lived experience, and policy context for {archetype} in South Africa. "
        f"Event or policy: {query[:400]}"
    )
    if document_text:
        focused += f"\n\nDocument context: {document_text[:600]}"

    visited_urls: List[str] = []
    all_learnings: List[str] = []

    try:
        await _deep_research(focused, breadth, depth, visited_urls, all_learnings)
    except Exception as e:
        logger.warning(f"Deep research loop failed for {archetype}: {e}")
        return archetype, ""

    if not all_learnings:
        return archetype, ""

    text = "\n".join(f"- {l}" for l in all_learnings[:15])
    if visited_urls:
        text += "\n\nSources: " + ", ".join(visited_urls[:5])

    logger.info(f"Deep research complete for {archetype}: {len(all_learnings)} learnings, {len(visited_urls)} URLs")
    return archetype, text


# ---------------------------------------------------------------------------
# Public sync API (called from Flask)
# ---------------------------------------------------------------------------

def _run_in_thread(archetype: str, query: str, document_text: str, breadth: int, depth: int) -> tuple:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_research_one(archetype, query, document_text, breadth, depth))
    finally:
        loop.close()


def research_archetypes(
    archetypes: List[str],
    query: str,
    document_text: str = "",
    breadth: int = 2,
    depth: int = 2,
) -> Dict[str, str]:
    """
    Research multiple SA archetypes in parallel.

    Returns Dict[archetype → research_text]. Returns {} if FIRECRAWL_API_KEY
    is not set or if all searches fail. Never raises.
    """
    if not _is_available():
        logger.info("Deep research skipped: FIRECRAWL_API_KEY not configured")
        return {}

    results: Dict[str, str] = {}
    logger.info(f"Starting deep research for {len(archetypes)} archetypes (breadth={breadth}, depth={depth})")

    # Run sequentially — Firecrawl free tier rejects concurrent scrapes,
    # causing all but the first 3 parallel threads to silently fail.
    for arch in archetypes:
        try:
            _, text = _run_in_thread(arch, query, document_text, breadth, depth)
            if text:
                results[arch] = text
                logger.info(f"Research done: {arch}")
            else:
                logger.info(f"Research empty: {arch}")
        except Exception as e:
            logger.warning(f"Research failed for {arch}: {e}")

    return results
