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
from typing import Dict, List, Optional

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
        f'Return JSON: {{"queries": ["query1", "query2", ...]}}\n\n'
        f"These queries feed PERSONA generation, so bias them toward how REAL South Africans in this\n"
        f"situation actually live, decide, and react — not encyclopedic facts.\n"
        f"RULES:\n"
        f"- Every query must be anchored to South Africa (name SA places, institutions, or 'South Africa').\n"
        f"- Favour lived experience: daily routines, money pressures, fears, who they trust, what they say.\n"
        f"- Include AT LEAST ONE query for hard NUMBERS that set the real magnitudes of this situation\n"
        f"  (SA prices in rand, incomes/grants, data/transport costs, market size, adoption/pilot rates).\n"
        f"  These ground the scenario the personas reason against — phrasings like 'cost', 'price',\n"
        f"  'how much', 'statistics', 'survey 2025/2026' help surface them.\n"
        f"- Steer toward SA news, government, NGO, academic and community sources; avoid vendor/marketing\n"
        f"  pages and generic listicles. Phrasings like 'South Africa', 'survey', 'report', 'interview',\n"
        f"  'community' help.\n"
        f"- Do NOT research foreign products/markets for their own sake. If a foreign product is relevant,\n"
        f"  query how South Africans relate to that KIND of thing locally.\n"
        f"- Make the queries varied (different angle each), not rewordings of one search."
    )
    result = await _llm_json(prompt, system="You are a research assistant for South African persona research. Return only valid JSON.")
    queries = result.get("queries", [])
    if not queries:
        return [topic]
    return queries[:breadth]


async def _extract_learnings(query: str, content: str, url: str) -> List[str]:
    """Extract key learnings from scraped page content, biased to SA lived experience.

    The LLM returns typed, SA-tagged learnings so we can drop the ones with no SA
    relevance at the source (this is where foreign-product facts like a smart cane's
    overseas price get filtered out before they ever reach persona generation).
    Returns a flat list of strings (rendered "[type] text") for backward compat with
    callers; non-SA-relevant items are discarded here.
    """
    if not content or len(content) < 100:
        return []
    prompt = (
        f"Extract up to 5 learnings from this web page relevant to: {query}\n\n"
        f"URL: {url}\nContent (first 3000 chars):\n{content[:3000]}\n\n"
        f"These learnings feed South African PERSONA generation. Prioritise LIVED EXPERIENCE — what\n"
        f"shapes a real person's daily reality, attitudes, money pressures, fears, routines, and who\n"
        f"they trust — over encyclopedic facts or product specs.\n\n"
        f"For each learning return an object:\n"
        f'  {{"type": "stat|quote|behaviour|constraint|attitude", "sa_relevant": true/false, "text": "..."}}\n'
        f"- type: which kind of signal it is. behaviour/attitude/constraint shape persona VOICE;\n"
        f"  stat captures a hard NUMBER (a rand price, income, cost, percentage, market size) that\n"
        f"  grounds the SCENARIO the personas reason against — capture these too, with the number and\n"
        f"  its unit intact (e.g. 'R50/month subscription', '1GB data ~R85', 'child grant R530/child').\n"
        f"- sa_relevant: true ONLY if it describes South African people/conditions, or how South Africans\n"
        f"  relate to something. Mark foreign-only facts (e.g. an overseas product's price/features with\n"
        f"  no SA bearing) as false.\n"
        f"- text: a specific fact, statistic, quote, behaviour, or constraint. No vague summaries.\n\n"
        f'Return JSON: {{"learnings": [ {{...}}, {{...}} ]}}'
    )
    result = await _llm_json(prompt, system="You are a research analyst for South African personas. Return only valid JSON.")

    out: List[str] = []
    for item in result.get("learnings", []):
        # Tolerate the old flat-string shape if a model ignores the schema.
        if isinstance(item, str):
            out.append(item)
            continue
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        if not text:
            continue
        # Drop foreign-only findings at the source — they must never reach personas.
        if item.get("sa_relevant") is False:
            continue
        ltype = (item.get("type") or "").strip()
        out.append(f"[{ltype}] {text}" if ltype else text)
    return out


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


async def _research_one(archetype: str, query: str, document_text: str, breadth: int, depth: int, agent_context: Optional[Dict] = None) -> tuple:
    """Run iterative deep research for a single archetype. Returns (archetype, text)."""
    focused = (
        f"Socio-economic conditions, lived experience, and policy context for {archetype} in South Africa. "
        f"Event or policy: {query[:200]}"
    )
    if document_text:
        focused += f"\n\nDocument context: {document_text[:600]}"
    
    # Incorporate agent context into the research focus
    if agent_context:
        agents = agent_context.get("agents", [])
        if agents:
            agent_descriptions = []
            for agent in agents:
                name = agent.get("name", "")
                archetype_name = agent.get("archetype", "")
                description = agent.get("description", "")
                if name:
                    agent_desc = f"{name}"
                    if archetype_name:
                        agent_desc += f" ({archetype_name})"
                    if description:
                        agent_desc += f": {description}"
                    agent_descriptions.append(agent_desc)
            
            if agent_descriptions:
                focused += f"\n\nResearch should consider perspectives from: {', '.join(agent_descriptions)}"

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

def _run_in_thread(archetype: str, query: str, document_text: str, breadth: int, depth: int, agent_context: Optional[Dict] = None) -> tuple:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_research_one(archetype, query, document_text, breadth, depth, agent_context))
    finally:
        loop.close()


def research_archetypes(
    archetypes: List[str],
    query: str,
    document_text: str = "",
    breadth: int = 2,
    depth: int = 2,
    agent_context: Optional[Dict] = None,
) -> Dict[str, str]:
    """
    Research multiple SA archetypes in parallel.

    Returns Dict[archetype → research_text]. Returns {} if FIRECRAWL_API_KEY
    is not set or if all searches fail. Never raises.
    
    Args:
        archetypes: List of archetype names to research
        query: The research query/topic
        document_text: Optional document context to guide research
        breadth: Number of search queries per research iteration
        depth: Depth of recursive research
        agent_context: Optional dict containing custom agent context to shape research
    """
    if not _is_available():
        logger.info("Deep research skipped: FIRECRAWL_API_KEY not configured")
        return {}

    results: Dict[str, str] = {}
    logger.info(f"Starting deep research for {len(archetypes)} archetypes (breadth={breadth}, depth={depth})")

    # Incorporate agent context into the research query
    enhanced_query = query
    if agent_context:
        agents = agent_context.get("agents", [])
        if agents:
            agent_names = [agent.get("name", "") for agent in agents if agent.get("name")]
            if agent_names:
                enhanced_query = f"{query} (focusing on perspectives from: {', '.join(agent_names)})"
                logger.info(f"Research enhanced with agent context: {agent_names}")

    # Run sequentially — Firecrawl free tier rejects concurrent scrapes,
    # causing all but the first 3 parallel threads to silently fail.
    for arch in archetypes:
        try:
            _, text = _run_in_thread(arch, enhanced_query, document_text, breadth, depth, agent_context)
            if text:
                results[arch] = text
                logger.info(f"Research done: {arch}")
            else:
                logger.info(f"Research empty: {arch}")
        except Exception as e:
            logger.warning(f"Research failed for {arch}: {e}")

    return results
