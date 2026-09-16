"""Web research, agent enrichment and archetype detection.

The rules behind the research routes. Four jobs:

  * `web` / `scrape` / `availability` — the web-research fallback chain (Jina, Serper,
    Firecrawl) and what is configured right now.
  * `enrich` — turn research findings into context for agent prompts.
  * `detect_archetypes` — ask the LLM who is in the seed document's cast.
  * `slim_paper` / `paper_id` — the shape a paper is stored in on a project.

No Flask. Services that are not configured raise `ServiceUnavailable`, so the
controller decides that this means 503.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Optional

from ..utils.logger import get_logger

logger = get_logger("fub.research_service")


class ServiceUnavailable(RuntimeError):
    """A required external service (Firecrawl, Serper, Jina) is not configured."""


class UnknownResearchType(ValueError):
    """The caller asked for a research type that does not exist."""


# ── web research ────────────────────────────────────────────────────────────────
def availability() -> Dict[str, Any]:
    """Which web research services are configured."""
    from .firecrawl_service import FirecrawlService
    from .serper_service import SerperService

    fc = FirecrawlService()
    serper = SerperService()

    services = []
    if fc.is_available():
        services.append("firecrawl")
    if serper.is_available():
        services.append("serper")

    return {
        "available": len(services) > 0,
        "services": services,
        "serper": {
            "available": serper.is_available(),
            "message": "Configured" if serper.is_available() else "Set SERPER_API_KEY in .env",
        },
        "firecrawl": {
            "available": fc.is_available(),
            "message": "Configured" if fc.is_available() else "Set FIRECRAWL_API_KEY in .env",
        },
    }


def scrape(url: str) -> Dict[str, Any]:
    """Scrape a single page with Firecrawl."""
    from .firecrawl_service import FirecrawlService

    service = FirecrawlService()
    if not service.is_available():
        raise ServiceUnavailable(
            "Firecrawl API key not configured. Set FIRECRAWL_API_KEY in .env")
    return service.scrape(url)


def web(query: str = "", url: str = "",
        agent_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Research a query, or scrape one URL, using whatever is configured.

    Order: a given URL goes straight to Firecrawl; otherwise deep research, then
    Serper + Firecrawl, then Serper alone.
    """
    from .firecrawl_service import FirecrawlService

    agent_context = agent_context or {}
    fc = FirecrawlService()

    # A specific URL bypasses search entirely.
    if url:
        if not fc.is_available():
            raise ServiceUnavailable(
                "No scraping service configured. Set FIRECRAWL_API_KEY in .env")
        return fc.scrape(url)

    from .deep_research_service import research_archetypes

    # Custom agent names shape the research query.
    enhanced_query = query
    agents = agent_context.get("agents") or []
    if agents:
        agent_names = [a.get("name", "") for a in agents if a.get("name")]
        if agent_names:
            enhanced_query = f"{query} (focusing on perspectives from: {', '.join(agent_names)})"

    result = research_archetypes(archetypes=["general"], query=enhanced_query,
                                 breadth=3, depth=2)
    if result:
        return {
            "success": True,
            "data": {"content": result.get("general", "")},
            "source": "deep_research",
            "agent_context": agent_context if agent_context else None,
        }

    from .serper_service import SerperService
    serper = SerperService()
    if serper.is_available() and fc.is_available():
        result = serper.search_and_scrape(query, num_results=5)
        if result.get("success"):
            return result
    if serper.is_available():
        return serper.search(query)

    if fc.is_available():
        return {
            "success": False,
            "message": "Serper not configured for web search. "
                       "Use 'url' field to scrape a specific page.",
            "query": query,
        }

    raise ServiceUnavailable(
        "No web research service configured. "
        "Set FIRECRAWL_API_KEY and/or SERPER_API_KEY in .env")


# ── enrichment ──────────────────────────────────────────────────────────────────
def enrich(query: str, archetypes: List[str], research_type: str = "literature",
           papers: Optional[List[Dict[str, Any]]] = None,
           urls: Optional[List[str]] = None) -> Dict[str, Any]:
    """Build enriched prompt context for each archetype.

    Literature enrichment searches for papers when none are supplied. Web enrichment
    tries deep research, then Serper + Firecrawl, then the caller's own URLs.
    """
    from .agent_enricher import AgentContextEnricher

    if research_type == "literature":
        papers = papers or []
        if not papers:
            from .literature_service import LiteratureSearchService
            results = LiteratureSearchService(max_results_per_source=5).search(query)
            papers = results.get("papers", [])
        return AgentContextEnricher.enrich_from_literature(papers, archetypes)

    if research_type != "web":
        raise UnknownResearchType(f"Unknown research type: {research_type}")

    from .deep_research_service import _is_available, research_archetypes
    from .firecrawl_service import FirecrawlService
    from .serper_service import SerperService

    fc = FirecrawlService()
    serper = SerperService()
    urls = urls or []

    combined: List[str] = []
    enriched: Dict[str, Any] = {}

    def from_web() -> Dict[str, Any]:
        return AgentContextEnricher.enrich_from_web_research(
            {"success": True, "content": "\n\n---\n\n".join(combined)}, archetypes)

    if _is_available():
        result = research_archetypes(archetypes=archetypes, query=query, breadth=3, depth=2)
        if result:
            combined.append("\n\n".join(result.values()))
            enriched = from_web()

    if not enriched and serper.is_available() and fc.is_available():
        result = serper.search_and_scrape(query, num_results=5)
        if result.get("success"):
            for item in result.get("scraped_content", []):
                if item.get("content"):
                    combined.append(item["content"])
            enriched = from_web()

    if not enriched and fc.is_available() and urls:
        for url in urls:
            r = fc.scrape(url)
            if r.get("success"):
                combined.append(r["content"][:1500])
        if combined:
            enriched = from_web()

    if not enriched:
        raise ServiceUnavailable(
            "Web research not available for enrichment. "
            "Configure Serper + Firecrawl, or provide URLs")
    return enriched


# ── archetype detection ─────────────────────────────────────────────────────────
#: Who can appear in a policy cast.
POLICY_TAXONOMY = """CIVIC/ESTABLISHMENT: civic_moderate, community_leader, institutional_loyalist
ACTIVISM: political_activist, student_activist
COMMUNITY: street_committee_chair, traditional_authority, community_organizer, spaza_shop_owner
ECONOMIC: taxi_operator, informal_trader, small_business_owner, gig_worker, unemployed_youth
CRIMINAL/GANG: gang_member, syndicates, mob_follower, opportunist_looter, violent_agitator, criminal_opportunist, community_protector
VULNERABLE: gbv_advocate, foreign_national, person_with_disability, elderly_grant_recipient, grant_dependent_survivor
DISENGAGED: disillusioned_dropout, conspiracy_spreader, whistleblower
PROFESSIONAL: nurse_healthcare_worker, teacher, community_journalist, ngo_worker
SECURITY: police_officer, soldier, private_security, park_ranger"""

#: Who can appear in a product cast. A product sim models a market, so the policy and
#: security lines are deliberately absent — they leaked SAPS into product runs.
PRODUCT_TAXONOMY = """CUSTOMERS/USERS: civic_moderate, unemployed_youth, gig_worker, student_activist
ECONOMIC: informal_trader, small_business_owner, spaza_shop_owner, taxi_operator
PROFESSIONAL: nurse_healthcare_worker, teacher, community_journalist, ngo_worker
COMMUNITY: community_leader, community_organizer
VULNERABLE: foreign_national, person_with_disability, elderly_grant_recipient, grant_dependent_survivor"""


def detect_archetypes(document_text: str, query: str = "", mode: str = "policy") -> List[str]:
    """Ask the LLM which actor archetypes the seed document contains.

    The document is the source of truth for who is in the cast. We deliberately do NOT
    keyword-guess archetypes from the text: substring matching on generic words
    ("crime", "reform") pulled SECURITY/policy actors (e.g. SAPS) into product sims
    that had no link to policing. If the LLM cannot infer a cast, we fall back to a
    single neutral, mode-appropriate set rather than guessing institutions.
    """
    from openai import OpenAI

    from ..config import Config

    client = OpenAI(api_key=Config.LLM_API_KEY, base_url=Config.LLM_BASE_URL)
    is_product = mode == "product"

    if is_product:
        taxonomy = PRODUCT_TAXONOMY
        intent = "These archetypes are the customer/user types for a product simulation."
    else:
        taxonomy = POLICY_TAXONOMY
        intent = ("These archetypes will be used to research current real-world "
                  "conditions for a policy simulation.")

    prompt = f"""Analyze this document and identify the key actor archetypes present.
{intent}

Document excerpt (first 3000 chars):
{document_text[:3000]}

{"Research query: " + query if query else ""}

Choose archetypes from this taxonomy (pick only those clearly present in the document):

{taxonomy}

Return ONLY a JSON array of archetype strings, e.g. ["informal_trader", "unemployed_youth", "taxi_operator"]
No explanation, no extra text."""

    try:
        response = client.chat.completions.create(
            model=Config.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content":
                    "You are an expert in South African socio-economics. "
                    "Return ONLY a JSON array of archetype strings."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=200,
        )
        result = json.loads(response.choices[0].message.content.strip())
        if isinstance(result, list):
            found = [str(a).strip() for a in result if str(a).strip()]
            if found:
                return found
        elif isinstance(result, dict):
            for key in ("archetypes", "actors", "types"):
                if isinstance(result.get(key), list):
                    found = [str(a).strip() for a in result[key] if str(a).strip()]
                    if found:
                        return found
    except Exception as e:  # noqa: BLE001 - a failed detection must not kill the run
        logger.warning(f"Archetype LLM detection failed: {e}")

    # Neutral fallback only — used when the LLM call fails or returns nothing, so a run
    # is never killed. No keyword/topic guessing: it must not invent a cast the seed
    # document doesn't support (that is what leaked SAPS into product sims).
    fallback = (["civic_moderate", "small_business_owner", "unemployed_youth"] if is_product
                else ["civic_moderate", "community_leader", "unemployed_youth"])
    logger.info(f"Archetype detection fell back to neutral {mode} cast: {fallback}")
    return fallback


# ── papers saved on a project ───────────────────────────────────────────────────
def paper_id(p: Dict[str, Any]) -> str:
    """Stable id for de-dup. Prefer the search id, else fall back to URL/title."""
    return str(p.get("id") or p.get("url") or p.get("title") or "").strip()


def slim_paper(p: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only the fields we care about when storing a paper on a project."""
    authors = p.get("authors")
    return {
        "id":       paper_id(p),
        "title":    p.get("title", ""),
        "authors":  authors if isinstance(authors, list) else [str(p.get("authors", ""))],
        "year":     p.get("year"),
        "source":   p.get("source", ""),
        "abstract": p.get("abstract", ""),
        "url":      p.get("url", ""),
    }


# ── literature ──────────────────────────────────────────────────────────────────
#: File types accepted for an uploaded paper. A tuple, not a set, so the error
#: message listing them is the same every time.
ALLOWED_PAPER_EXTENSIONS = (".md", ".pdf", ".txt")

_literature = None


def get_literature_service():
    """The shared literature service. Built once: it loads its metadata on init."""
    global _literature
    if _literature is None:
        from .literature_service import LiteratureSearchService
        _literature = LiteratureSearchService(max_results_per_source=10)
    return _literature


def search(query: str, sources: Optional[List[str]] = None,
           max_results: int = 10) -> Dict[str, Any]:
    """Search academic literature. `max_results` is per source."""
    from .literature_service import LiteratureSearchService
    return LiteratureSearchService(max_results_per_source=max_results).search(query, sources)


def local_papers() -> List[Dict[str, Any]]:
    """Every locally stored paper."""
    return get_literature_service().get_local_papers()


def add_paper(title: str, authors: List[str], year: Optional[int], abstract: str,
              doi: Optional[str] = None, file_path: Optional[str] = None):
    """Add a paper to the local collection. Returns the stored Paper."""
    return get_literature_service().add_local_paper(
        title=title, authors=authors, year=year, abstract=abstract,
        doi=doi, file_path=file_path)


def save_uploaded_paper(write: Callable[[str], None], title: str, ext: str) -> str:
    """Write an uploaded paper into the papers directory; return its path.

    `write` is handed the destination path, so the web framework's upload object
    stays in the controller.
    """
    papers_dir = get_literature_service()._get_local_papers_dir()
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
    # NOTE: getmtime('.') is the directory's mtime, not the clock, so this suffix
    # barely changes and two uploads of the same title can collide. Moved verbatim
    # from app/api/research.py; worth fixing on its own, not inside a refactor.
    file_path = papers_dir / f"{safe_title[:50]}_{int(os.path.getmtime('.'))}{ext}"
    write(str(file_path))
    return str(file_path)


def serper_search(query: str, num_results: int = 10) -> Dict[str, Any]:
    """Search Google via Serper."""
    from .serper_service import SerperService

    service = SerperService()
    if not service.is_available():
        raise ServiceUnavailable(
            "Serper API key not configured. Set SERPER_API_KEY in .env")
    return service.search(query, num_results)


# ── deep research ───────────────────────────────────────────────────────────────
#: Each archetype takes roughly two minutes of web research, so the cast is capped.
MAX_DEEP_ARCHETYPES = 3


class NoArchetypes(ValueError):
    """No cast could be worked out from the document."""


def deep(query: str, document_text: str = "",
         archetypes: Optional[List[str]] = None, mode: str = "policy") -> Dict[str, Any]:
    """Research current conditions for each archetype in the document.

    Detects the cast from `document_text` when none is given. Raises NoArchetypes
    when there is still nothing to research, and ServiceUnavailable when no scraping
    service is configured.
    """
    from .deep_research_service import _is_available, research_archetypes

    archetypes = (archetypes or [])[:MAX_DEEP_ARCHETYPES]

    if not archetypes and document_text:
        archetypes = detect_archetypes(document_text, query, mode)
        if not archetypes:
            raise NoArchetypes("Could not detect archetypes from document. "
                               "Please provide archetypes manually.")
        archetypes = archetypes[:MAX_DEEP_ARCHETYPES]
        logger.info(f"Auto-detected {len(archetypes)} archetypes from document: {archetypes}")

    if not archetypes:
        raise NoArchetypes("At least one archetype is required "
                           "(provide archetypes or document_text)")

    if not _is_available():
        raise ServiceUnavailable(
            "Deep research not available. Set FIRECRAWL_API_KEY or JINA_API_KEY in .env")

    logger.info(f"Deep research starting: {len(archetypes)} archetypes "
                f"for query: {query[:80]}...")
    results = research_archetypes(archetypes=archetypes, query=query,
                                  document_text=document_text, breadth=3, depth=2)

    enrichment = {}
    for archetype, content in results.items():
        if content:
            enrichment[archetype] = content
            logger.info(f"Enrichment data captured for {archetype} ({len(content)} chars)")

    completed = len(enrichment)
    status = "completed" if completed == len(archetypes) else "partial"
    if completed == 0:
        status = "failed"
    logger.info(f"Deep research {status}: {completed}/{len(archetypes)} archetypes enriched")

    return {
        "success": status != "failed",
        "enrichment": enrichment,
        "archetypes_researched": len(archetypes),
        "archetypes_completed": completed,
        "status": status,
    }
