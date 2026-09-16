"""Building a seed briefing from live web research.

When the user has no document to upload, this stands in for one: search the web for
their topic, scrape the top pages, and have the LLM synthesise a structured briefing
the simulation can use as its `simulation_requirement`.

Two rules are load-bearing here, both about keeping the briefing honest:

  * **Only real figures from the sources.** The "Key figures" block asks for concrete
    numbers (prices, incomes, costs) because those are the magnitudes the simulated
    people reason against. It says so three ways, because an LLM asked for numbers
    will otherwise invent plausible ones.
  * **Never a forecast.** The prompt forbids stating or implying how many people would
    buy, adopt or approve. A seed briefing is context, not a verdict.

No Flask here. The two failure modes are exceptions, so the controller decides what
HTTP status each deserves.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger

logger = get_logger("fub.seed_service")

#: Scrape 4 pages, not 6. The seed endpoint scrapes live pages serially, so each extra
#: page adds real wall-clock time and bloats the synthesis prompt. 4 keeps the briefing
#: well-grounded while staying under the frontend timeout.
MAX_SOURCES = 4

#: Jina's search endpoint rejects long queries with a 422, so the search call is
#: truncated to this. The full topic is still used for synthesis.
MAX_QUERY_CHARS = 200


class NoSources(RuntimeError):
    """Nothing could be scraped, so there is nothing to synthesise from."""


class SynthesisFailed(RuntimeError):
    """The LLM call that writes the briefing failed."""


@dataclass
class Seed:
    """A finished briefing and what it was built from."""
    seed_text: str
    sources: List[Dict[str, str]]
    scraped_count: int
    char_count: int
    judge: Optional[Dict[str, Any]] = None


def scrape_sources(topic: str, extra_urls: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """Search and scrape up to MAX_SOURCES pages, plus any URLs the user supplied.

    Jina is tried first (more generous free tier); Serper + Firecrawl is the fallback,
    and fires when Jina returned nothing or was never configured. Every failure is
    logged and swallowed: a single dead page must not fail the whole briefing.
    """
    from .firecrawl_service import FirecrawlService
    from .jina_service import JinaService
    from .serper_service import SerperService

    fc = FirecrawlService()
    serper = SerperService()
    jina = JinaService()

    scraped: List[Dict[str, str]] = []
    query = topic if len(topic) <= MAX_QUERY_CHARS else topic[:MAX_QUERY_CHARS].rsplit(" ", 1)[0]

    if jina.api_key:
        try:
            combined = jina.search_and_scrape(query, num_results=MAX_SOURCES)
            if combined.get("success"):
                scraped.extend(_harvest(combined))
        except Exception as e:  # noqa: BLE001 - a dead search must not fail the seed
            logger.warning(f"Jina search_and_scrape failed: {e}")

    if not scraped and (serper.is_available() or fc.is_available()):
        try:
            combined = serper.search_and_scrape(query, num_results=MAX_SOURCES)
            if combined.get("success"):
                scraped.extend(_harvest(combined))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Serper+Firecrawl search failed: {e}")

    # User-supplied URLs are scraped on top: Jina first, Firecrawl as the fallback.
    for url in (extra_urls or [])[:3]:
        r = jina.scrape(url) if jina.api_key else {"success": False}
        if not r.get("success") and fc.is_available():
            try:
                r = fc.scrape(url)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Firecrawl scrape failed for {url}: {e}")
                continue
        if r.get("success"):
            scraped.append({
                "url": url,
                "title": r.get("title", url),
                "content": (r.get("content") or "")[:3000],
            })

    return scraped


def _harvest(combined: Dict[str, Any]) -> List[Dict[str, str]]:
    """Pull the usable pages out of a search+scrape result."""
    return [{
        "url": item["url"],
        "title": item.get("title", ""),
        "content": item["content"][:3000],
    } for item in combined.get("scraped_content", []) if item.get("content")]


def _key_figures_section(citations: str) -> str:
    """The shared 'Key figures' block.

    Framed hard as context to reason against, never lines to recite and never a
    forecast: the sim must not turn these into a "% who would buy" verdict.
    """
    return (
        f"## Key figures\n"
        f"  - Pull the CONCRETE NUMBERS from the sources that define the real magnitudes of this\n"
        f"    situation: prices (in rand), incomes/grants, data/transport/other costs, market sizes,\n"
        f"    adoption or pilot rates, percentages, timelines. Give each as 'figure — what it means'\n"
        f"    with an inline source {citations}.\n"
        f"  - Only real figures FROM THE SOURCES. Do NOT invent, estimate, or round into a made-up number.\n"
        f"  - These are the magnitudes the simulated people will REASON AGAINST (e.g. weighing a price\n"
        f"    against their real income). They are CONTEXT, not predictions — never state or imply how\n"
        f"    many people would buy, adopt, or approve. No forecasts, no success scores.\n\n"
    )


def build_prompt(topic: str, mode: str, scraped: List[Dict[str, str]]) -> str:
    """The synthesis prompt for a product or a policy briefing."""
    sources_blob = "\n\n".join(
        f"### Source {i+1}: {s['title']}\n{s['content']}" for i, s in enumerate(scraped)
    )
    citations = ", ".join(f"[{i+1}]" for i in range(len(scraped)))
    key_figures_section = _key_figures_section(citations)

    if mode == "product":
        return (
            f"You are preparing a seed briefing document for a South African product stress-test simulation.\n\n"
            f"PRODUCT IDEA: {topic}\n\n"
            f"Below are {len(scraped)} articles scraped from the web. Synthesize them into a "
            f"structured briefing (~1000-1400 words) that a simulation engine will use to generate "
            f"agent personas and run a multi-agent product simulation.\n\n"
            f"GEOGRAPHIC PRIORITY RULES:\n"
            f"- PRIMARY: Focus on the South African market. What exists in SA? Who are the local players?\n"
            f"- SECONDARY: International competitors with confirmed SA presence (e.g. Netflix, Uber, Showmax).\n"
            f"- CONTEXT ONLY: Foreign competitors with NO SA presence — include ONLY for customer insight "
            f"reference (a foreign competitor product can show what users value, without being a local actor).\n"
            f"- Do NOT let foreign competitors dominate the briefing. They are reference points, not primary actors.\n\n"
            f"REQUIRED STRUCTURE:\n"
            f"## Background\n"
            f"  - What is the product idea? What problem does it solve? Where in SA is this relevant?\n\n"
            f"## SA market context\n"
            f"  - What exists in South Africa today for this problem? Local competitors, alternatives, status-quo.\n\n"
            + key_figures_section +
            f"## Key customer segments\n"
            f"  - List 5-8 distinct South African customer types who would use this product.\n"
            f"  - These MUST be REAL HUMAN people-types (e.g. 'blind commuters in Soweto', 'spaza owners',\n"
            f"    'office workers with low vision') — NOT products, apps, brands, programmes, or companies.\n"
            f"  - For each: their profile, their pain points, what they currently use instead.\n\n"
            f"NON-AGENT RULE: Products, apps, brands, competitor products, and programmes (e.g. a named app,\n"
            f"a device, a campaign) are CONTEXT ONLY. Mention them under competitive landscape, never as\n"
            f"customer segments or actors. The simulation's agents are PEOPLE (and the businesses that buy),\n"
            f"never products. A competitor PRODUCT is not an actor; the PEOPLE who use or sell it are.\n\n"
            f"## Competitive landscape\n"
            f"  - SA-based competitors (primary weight).\n"
            f"  - International with SA presence (secondary weight).\n"
            f"  - Global context competitors (reference only — include customer insights, not market dominance).\n\n"
            f"## Barriers and realities\n"
            f"  - What SA-specific barriers exist? (data costs, load-shedding, income, trust, regulation)\n\n"
            f"Cite sources inline using {citations}. Do not invent facts not in the sources. "
            f"Write in clear, declarative prose suitable for downstream LLM ingestion.\n\n"
            f"SOURCES:\n{sources_blob}"
        )

    return (
        f"You are preparing a seed briefing document for a South African policy simulation.\n\n"
        f"TOPIC: {topic}\n\n"
        f"Below are {len(scraped)} articles scraped from the web. Synthesize them into a "
        f"structured briefing (~1000-1400 words) that a simulation engine will use to generate "
        f"agent personas and run a multi-agent simulation.\n\n"
        f"REQUIRED STRUCTURE:\n"
        f"## Background\n"
        f"  - Set the scene. What is the situation? Where (province, township, sector)? Recent timeline.\n\n"
        + key_figures_section +
        f"## Key actors and their interests\n"
        f"  - List 5-8 distinct actor types involved (e.g. taxi_operator, community_leader, police_officer).\n"
        f"  - These MUST be REAL HUMAN people-types — NOT organisations-as-names, programmes, or campaigns.\n"
        f"    (A genuine institution may be an actor, but describe it as the PEOPLE who speak for it.)\n"
        f"  - For each: their role, their concerns, their relationship to the issue.\n"
        f"  - Be specific to South African context. Use real archetypes from the articles.\n\n"
        f"NON-AGENT RULE: Programmes, campaigns, brands, and abstract initiatives are CONTEXT, not actors.\n"
        f"The simulation's agents are PEOPLE and the institutions whose human representatives speak.\n\n"
        f"## Recent events\n"
        f"  - Bulleted timeline of concrete events from the articles. Cite sources inline like [1], [2].\n\n"
        f"## Tensions and dynamics\n"
        f"  - What conflicts exist between the actors? Where are the friction points?\n\n"
        f"## Policy environment\n"
        f"  - What policies, government responses, or proposals are in play? What's contested?\n\n"
        f"Cite sources inline using {citations}. Do not invent facts not in the sources. "
        f"Write in clear, declarative prose suitable for downstream LLM ingestion.\n\n"
        f"SOURCES:\n{sources_blob}"
    )


def generate(topic: str, mode: str = "policy",
             extra_urls: Optional[List[str]] = None) -> Seed:
    """Scrape, synthesise and (if enabled) judge a seed briefing.

    Raises NoSources when nothing could be scraped, and SynthesisFailed when the
    LLM call fails — the caller turns those into 502 and 500.
    """
    from ..utils.llm_client import LLMClient

    t0 = time.time()
    scraped = scrape_sources(topic, extra_urls)
    logger.info(f"Seed scrape done: {len(scraped)} sources in {time.time() - t0:.1f}s "
                f"(topic={topic[:60]})")

    if not scraped:
        raise NoSources(
            "No content could be scraped. "
            "Check that FIRECRAWL_API_KEY is valid and (optionally) SERPER_API_KEY is set "
            "for Google search. You can also pass extra_urls explicitly."
        )

    t_syn = time.time()
    synthesis_prompt = build_prompt(topic, mode, scraped)
    system_msg = (
        "You are a research analyst specializing in South African contexts. "
        "Produce concise, fact-grounded briefings. "
        + ("For product simulations, prioritize SA market context; foreign competitors are reference only."
           if mode == "product" else
           "For policy simulations, focus on SA socio-political dynamics.")
    )

    # The source list is appended to the briefing for transparency.
    sources_md = "\n\n---\n\n## Sources\n" + "\n".join(
        f"[{i+1}] [{s['title'] or s['url']}]({s['url']})" for i, s in enumerate(scraped)
    )

    llm = LLMClient()

    # Synthesis is a callable so the advisory judge can regenerate ONCE on a low score.
    # The retry hint is qualitative only — it must not invite invented facts, because
    # the "no invented facts" criterion still applies on the retry.
    def generate_briefing(prev_judge=None):
        retry_hint = ""
        if prev_judge is not None and prev_judge.reasoning:
            retry_hint = (
                f"\n\nA previous draft scored low. Improve on this feedback while staying "
                f"strictly grounded in the SOURCES (do NOT invent facts to satisfy it):\n"
                f"{prev_judge.reasoning}\n"
            )
        text = llm.chat(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": synthesis_prompt + retry_hint},
            ],
            temperature=0.4,
            max_tokens=2200,
        )
        return text.strip() + sources_md

    judge_result = None
    try:
        from .judge_service import (get_judge_service, judge_best_of, judge_enabled,
                                    record_judgement)
        if judge_enabled():
            svc = get_judge_service()
            # The judge sees the same sources the briefing was synthesised from, so
            # "no invented facts" is checked against evidence rather than vibes.
            judge_sources = [
                {"title": s["title"] or s["url"], "excerpt": s["content"][:600]}
                for s in scraped[:10]
            ]
            seed_text, judge_result, regenerated = judge_best_of(
                generate=generate_briefing,
                judge=lambda t: svc.judge_seed_briefing(t, mode, topic, sources=judge_sources),
            )
            record_judgement("seed_briefing", judge_result, run_id=topic[:80],
                             regenerated=regenerated)
            if regenerated:
                logger.info(f"Seed briefing regenerated once on judge feedback (topic={topic})")
        else:
            seed_text = generate_briefing()
    except Exception as e:  # noqa: BLE001 - reported to the caller as a 500
        logger.error(f"Synthesis LLM call failed: {e}")
        raise SynthesisFailed(str(e)) from e

    logger.info(
        f"Seed synthesis done in {time.time() - t_syn:.1f}s "
        f"(total {time.time() - t0:.1f}s, {len(seed_text)} chars)"
    )

    return Seed(
        seed_text=seed_text,
        sources=[{"url": s["url"], "title": s["title"]} for s in scraped],
        scraped_count=len(scraped),
        char_count=len(seed_text),
        judge=judge_result.to_dict() if judge_result else None,
    )
