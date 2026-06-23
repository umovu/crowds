"""
Research API Routes

Endpoints for literature search and research context management.
"""

import os
import json
import logging
from typing import Dict, Tuple
from flask import Blueprint, request, jsonify, current_app

from ..services.literature_service import LiteratureSearchService
from ..services.deep_research_service import _is_available
from ..utils.logger import get_logger

logger = get_logger("fub.research")

research_bp = Blueprint("research", __name__)


def _extract_people_type_spec(web_context: str, group: str, context: str = "") -> list:
    """Distil raw web text into a list of SA-grounded PEOPLE-TYPE segments.

    This is the binding step between web research and persona generation. Web text
    is never handed to the persona generator directly — it goes through here first,
    so foreign products/brands/places with no SA relevance (the WeWALK leak) are
    dropped to context and can never define WHO a persona is. The persona generator
    downstream only ever sees these distilled SA people-type segments.

    Returns a list of dicts: {segment, who, where, pain_points}. Empty list on any
    failure — callers must treat an empty spec as "no usable grounding" and fall
    back to ungrounded generation rather than feeding raw web text through.
    """
    from ..utils.llm_client import LLMClient

    if not web_context.strip():
        return []

    context_line = f"\nThey are being modelled for their reaction to: {context}\n" if context else ""
    prompt = f"""You are distilling web research into REAL SOUTH AFRICAN people-type segments
for a simulation about this group:

GROUP: {group}{context_line}

Below is raw web research. Extract ONLY the kinds of REAL HUMAN PEOPLE in South Africa
who belong to (or directly interact with) this group. Each segment is a type of person,
grounded in SA reality — never a product, app, brand, device, company, or foreign entity.

HARD RULES:
- A product/app/brand/device (e.g. a named smart cane, an overseas app) is CONTEXT, not a
  person. Never turn one into a segment. If the web text is mostly about a foreign product,
  extract the SA PEOPLE who would use that *kind* of thing, not the product itself.
- Every segment must be plausibly present in South Africa. Drop anything foreign with no SA
  relevance.
- Segments capture the genuine diversity WITHIN the group (different ages, incomes, attitudes,
  locations) — not one stereotype.

RAW WEB RESEARCH:
{web_context}

Return ONLY valid JSON of the form:
{{"segments": [
  {{"segment": "short label, e.g. 'blind commuter, Soweto'",
    "who": "1-2 sentences on this person-type",
    "where": "SA place / province / setting",
    "pain_points": ["concrete pain point", "..."]}}
]}}
Return 4-8 distinct segments. No explanation."""

    try:
        llm = LLMClient()
        parsed = llm.chat_json(
            messages=[
                {"role": "system", "content":
                    "You extract real South African people-type segments from web research. "
                    "Products, brands, and foreign entities are context, never people. Return ONLY JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1500,
        )
    except Exception as e:
        logger.warning(f"People-type spec extraction failed (falling back to ungrounded): {e}")
        return []

    segments = []
    if isinstance(parsed, dict):
        segments = parsed.get("segments", parsed.get("people_types", []))
    elif isinstance(parsed, list):
        segments = parsed
    return [s for s in segments if isinstance(s, dict) and s.get("segment")]


def _format_people_type_spec(segments: list) -> str:
    """Render a people-type spec as the constraint block fed to the persona LLM."""
    lines = []
    for i, s in enumerate(segments, 1):
        pains = s.get("pain_points") or []
        pains_str = "; ".join(str(p) for p in pains) if isinstance(pains, list) else str(pains)
        lines.append(
            f"{i}. {s.get('segment', '')} — {s.get('who', '')} "
            f"[where: {s.get('where', 'South Africa')}]"
            + (f" [pain points: {pains_str}]" if pains_str else "")
        )
    return "\n".join(lines)

_literature_service = None


def get_literature_service() -> LiteratureSearchService:
    global _literature_service
    if _literature_service is None:
        _literature_service = LiteratureSearchService(max_results_per_source=10)
    return _literature_service


@research_bp.route("/search", methods=["POST"])
def search_literature():
    """
    Search academic literature across all configured sources.

    Request body:
    {
        "query": "search query string",
        "sources": ["arxiv", "openalex", "crossref", "local"],  // optional
        "max_results": 10  // optional, default 10
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Query is required"}), 400

    sources = data.get("sources")
    if sources and not isinstance(sources, list):
        return jsonify({"error": "sources must be a list"}), 400

    max_results = data.get("max_results", 10)
    if not isinstance(max_results, int) or max_results < 1 or max_results > 50:
        return jsonify({"error": "max_results must be between 1 and 50"}), 400

    try:
        service = LiteratureSearchService(max_results_per_source=max_results)
        results = service.search(query, sources)

        logger.info(f"Literature search: query='{query}', sources={sources}, results={results['total']}")

        return jsonify(results)

    except Exception as e:
        logger.error(f"Literature search failed: {e}")
        return jsonify({"error": str(e)}), 500


@research_bp.route("/search/<source>", methods=["POST"])
def search_source_only(source):
    """Search only a specific source (arxiv, openalex, crossref, local)."""
    if source not in ["arxiv", "openalex", "crossref", "local"]:
        return jsonify({"error": f"Unknown source: {source}"}), 400

    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Query is required"}), 400

    max_results = data.get("max_results", 10)

    try:
        service = LiteratureSearchService(max_results_per_source=max_results)
        results = service.search(query, sources=[source])
        return jsonify(results)

    except Exception as e:
        logger.error(f"{source} search failed: {e}")
        return jsonify({"error": str(e)}), 500


@research_bp.route("/local", methods=["GET"])
def get_local_papers():
    """Get all locally uploaded papers."""
    try:
        service = get_literature_service()
        papers = service.get_local_papers()
        return jsonify({
            "papers": papers,
            "total": len(papers)
        })
    except Exception as e:
        logger.error(f"Failed to get local papers: {e}")
        return jsonify({"error": str(e)}), 500


@research_bp.route("/local", methods=["POST"])
def add_local_paper():
    """
    Add a local paper manually (without file upload).

    Request body:
    {
        "title": "Paper title",
        "authors": ["Author 1", "Author 2"],
        "year": 2024,
        "abstract": "Paper abstract...",
        "doi": "10.xxxx/xxxxx"  // optional
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400

    authors = data.get("authors", [])
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(",")]

    year = data.get("year")
    if year:
        try:
            year = int(year)
        except (ValueError, TypeError):
            year = None

    abstract = data.get("abstract", "")
    doi = data.get("doi")

    try:
        service = get_literature_service()
        paper = service.add_local_paper(
            title=title,
            authors=authors,
            year=year,
            abstract=abstract,
            doi=doi
        )

        return jsonify({
            "success": True,
            "paper": {
                "id": paper.id,
                "title": paper.title,
                "authors": paper.authors,
                "year": paper.year,
                "source": paper.source
            }
        }), 201

    except Exception as e:
        logger.error(f"Failed to add local paper: {e}")
        return jsonify({"error": str(e)}), 500


@research_bp.route("/local/upload", methods=["POST"])
def upload_local_paper():
    """
    Upload a local paper file (PDF, MD, or TXT).

    Multipart form data:
    - file: The paper file (required)
    - title: Paper title (optional, extracted from file if not provided)
    - authors: Comma-separated authors (optional)
    - year: Publication year (optional)
    - abstract: Paper abstract (optional)
    - doi: DOI (optional)
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    # Check file extension
    allowed_extensions = {'.pdf', '.md', '.txt'}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        return jsonify({"error": f"File type not allowed. Allowed: {', '.join(allowed_extensions)}"}), 400

    # Get form data
    title = request.form.get('title', '').strip() or file.filename
    authors_str = request.form.get('authors', '')
    authors = [a.strip() for a in authors_str.split(',')] if authors_str else []
    year = request.form.get('year')
    year = int(year) if year and year.isdigit() else None
    abstract = request.form.get('abstract', '')
    doi = request.form.get('doi', '')

    # Save file
    try:
        service = get_literature_service()
        papers_dir = service._get_local_papers_dir()

        # Create safe filename
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_filename = f"{safe_title[:50]}_{int(os.path.getmtime('.'))}{ext}"
        file_path = papers_dir / safe_filename

        file.save(str(file_path))

        # Add paper to collection
        paper = service.add_local_paper(
            title=title,
            authors=authors,
            year=year,
            abstract=abstract,
            doi=doi,
            file_path=str(file_path)
        )

        return jsonify({
            "success": True,
            "paper": {
                "id": paper.id,
                "title": paper.title,
                "authors": paper.authors,
                "year": paper.year,
                "source": paper.source,
                "local_path": paper.local_path
            }
        }), 201

    except Exception as e:
        logger.error(f"Failed to upload paper: {e}")
        return jsonify({"error": str(e)}), 500


@research_bp.route("/web", methods=["POST"])
def web_research():
    """
    Perform web research using Firecrawl + Serper (deep research).

    Request body:
    {
        "query": "Research question or topic",
        "url": "https://...",   // optional, for direct scraping via Firecrawl
        "agent_context": {
            "agents": [
                {
                    "name": "agent_name",
                    "archetype": "agent_archetype",
                    "description": "agent_description",
                    "background": "agent_background"
                }
            ],
            "context_focus": "specific_focus_area"
        }   // optional, custom agent context to shape research
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    query = data.get("query", "").strip()
    url = data.get("url", "").strip()
    agent_context = data.get("agent_context", {})

    if not query and not url:
        return jsonify({"error": "Query or URL is required"}), 400

    try:
        from ..services.firecrawl_service import FirecrawlService

        fc = FirecrawlService()

        # If a specific URL is given, use Firecrawl directly
        if url:
            if not fc.is_available():
                return jsonify({
                    "error": "No scraping service configured. Set FIRECRAWL_API_KEY in .env"
                }), 503
            result = fc.scrape(url)
            return jsonify(result)

        # Use deep research service (Firecrawl + Jina + LLM)
        from ..services.deep_research_service import research_archetypes

        # Incorporate agent context into the research query
        enhanced_query = query
        if agent_context and agent_context.get("agents"):
            agents = agent_context.get("agents", [])
            if agents:
                agent_names = [agent.get("name", "") for agent in agents if agent.get("name")]
                if agent_names:
                    enhanced_query = f"{query} (focusing on perspectives from: {', '.join(agent_names)})"
        
        result = research_archetypes(
            archetypes=["general"],
            query=enhanced_query,
            breadth=3,
            depth=2,
        )
        if result:
            return jsonify({
                "success": True,
                "data": {"content": result.get("general", "")},
                "source": "deep_research",
                "agent_context": agent_context if agent_context else None
            })

        # Default: Serper search + Firecrawl scrape
        from ..services.serper_service import SerperService
        serper = SerperService()
        if serper.is_available() and fc.is_available():
            result = serper.search_and_scrape(query, num_results=5)
            if result.get("success"):
                return jsonify(result)
        if serper.is_available():
            result = serper.search(query)
            return jsonify(result)

        # Fallback: just Firecrawl scrape
        if fc.is_available():
            return jsonify({
                "success": False,
                "message": "Serper not configured for web search. Use 'url' field to scrape a specific page.",
                "query": query
            })

        return jsonify({
            "error": "No web research service configured. Set FIRECRAWL_API_KEY and/or SERPER_API_KEY in .env"
        }), 503

    except Exception as e:
        logger.error(f"Web research failed: {e}")
        return jsonify({"error": str(e)}), 500


@research_bp.route("/web/scrape", methods=["POST"])
def firecrawl_scrape():
    """
    Scrape a single webpage using Firecrawl API.

    Request body:
    {
        "url": "https://example.com/article"
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        from ..services.firecrawl_service import FirecrawlService

        service = FirecrawlService()
        if not service.is_available():
            return jsonify({
                "error": "Firecrawl API key not configured. Set FIRECRAWL_API_KEY in .env"
            }), 503

        result = service.scrape(url)
        return jsonify(result)

    except Exception as e:
        logger.error(f"Firecrawl scrape failed: {e}")
        return jsonify({"error": str(e)}), 500


@research_bp.route("/web/status", methods=["GET"])
def web_research_status():
    """Check availability of web research services."""
    try:
        from ..services.firecrawl_service import FirecrawlService
        from ..services.serper_service import SerperService

        fc = FirecrawlService()
        serper = SerperService()

        services = []
        if fc.is_available():
            services.append("firecrawl")
        if serper.is_available():
            services.append("serper")

        return jsonify({
            "available": len(services) > 0,
            "services": services,
            "serper": {
                "available": serper.is_available(),
                "message": "Configured" if serper.is_available() else "Set SERPER_API_KEY in .env"
            },
            "firecrawl": {
                "available": fc.is_available(),
                "message": "Configured" if fc.is_available() else "Set FIRECRAWL_API_KEY in .env"
            }
        })
    except Exception as e:
        return jsonify({
            "available": False,
            "error": str(e)
        }), 500


@research_bp.route("/enrich", methods=["POST"])
def enrich_agents():
    """
    Enrich agent context with research findings.

    Takes research results and generates enriched context for agent prompts.

    Request body:
    {
        "query": "Research query used for enrichment",
        "archetypes": ["informal_trader", "community_organizer"],
        "research_type": "literature" | "web",
        "papers": [...]  // optional, for literature enrichment
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    query = data.get("query", "").strip()
    archetypes = data.get("archetypes", [])
    research_type = data.get("research_type", "literature")

    if not query:
        return jsonify({"error": "Query is required"}), 400

    if not archetypes:
        return jsonify({"error": "At least one archetype is required"}), 400

    try:
        from ..services.agent_enricher import AgentContextEnricher

        enriched_context = {}

        if research_type == "literature":
            papers = data.get("papers", [])
            if not papers:
                # If no papers provided, do a search
                service = LiteratureSearchService(max_results_per_source=5)
                results = service.search(query)
                papers = results.get("papers", [])

            enriched_context = AgentContextEnricher.enrich_from_literature(
                papers, archetypes
            )

        elif research_type == "web":
            from ..services.deep_research_service import research_archetypes
            from ..services.firecrawl_service import FirecrawlService
            from ..services.serper_service import SerperService

            fc = FirecrawlService()
            serper = SerperService()
            urls = data.get("urls", [])

            context_source = ""
            combined = []
            enriched_context = {}

            # Try deep research service (Firecrawl + Jina + LLM)
            if _is_available():
                result = research_archetypes(
                    archetypes=archetypes,
                    query=query,
                    breadth=3,
                    depth=2,
                )
                if result:
                    context_source = "deep_research"
                    combined.append("\n\n".join(result.values()))
                    research_result = {
                        "success": True,
                        "content": "\n\n---\n\n".join(combined)
                    }
                    enriched_context = AgentContextEnricher.enrich_from_web_research(
                        research_result, archetypes
                    )

            if not enriched_context and serper.is_available() and fc.is_available():
                result = serper.search_and_scrape(query, num_results=5)
                if result.get("success"):
                    context_source = "serper+firecrawl"
                    for item in result.get("scraped_content", []):
                        content = item.get("content", "")
                        if content:
                            combined.append(content)
                    research_result = {
                        "success": True,
                        "content": "\n\n---\n\n".join(combined)
                    }
                    enriched_context = AgentContextEnricher.enrich_from_web_research(
                        research_result, archetypes
                    )

            if not enriched_context and fc.is_available() and urls:
                for url in urls:
                    r = fc.scrape(url)
                    if r.get("success"):
                        combined.append(r["content"][:1500])
                if combined:
                    context_source = "firecrawl"
                    research_result = {
                        "success": True,
                        "content": "\n\n---\n\n".join(combined)
                    }
                    enriched_context = AgentContextEnricher.enrich_from_web_research(
                        research_result, archetypes
                    )

            if not enriched_context:
                return jsonify({
                    "error": "Web research not available for enrichment. Configure Serper + Firecrawl, or provide URLs"
                }), 503

        else:
            return jsonify({"error": f"Unknown research type: {research_type}"}), 400

        return jsonify({
            "success": True,
            "query": query,
            "research_type": research_type,
            "archetypes": archetypes,
            "context": enriched_context,
            "enriched_count": len(enriched_context)
        })

    except Exception as e:
        logger.error(f"Agent enrichment failed: {e}")
        return jsonify({"error": str(e)}), 500


@research_bp.route("/web/search", methods=["POST"])
def serper_search():
    """
    Search Google via Serper API.

    Request body:
    {
        "query": "search topic",
        "num_results": 10  // optional, max 20
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Query is required"}), 400

    num_results = min(data.get("num_results", 10), 20)

    try:
        from ..services.serper_service import SerperService

        service = SerperService()
        if not service.is_available():
            return jsonify({
                "error": "Serper API key not configured. Set SERPER_API_KEY in .env"
            }), 503

        result = service.search(query, num_results)
        return jsonify(result)

    except Exception as e:
        logger.error(f"Serper search failed: {e}")
        return jsonify({"error": str(e)}), 500


@research_bp.route("/seed", methods=["POST"])
def generate_seed():
    """
    Generate seed material from web research when user doesn't have a document.

    Searches Google for the topic, scrapes top results via Firecrawl, then has
    the LLM synthesize a structured policy briefing that can be used as the
    simulation_requirement / seed document in place of an uploaded file.

    Request body:
    {
        "topic": "GBV response in rural KZN, taxi industry tensions",
        "extra_urls": ["https://..."]  // optional, scraped in addition to search results
    }

    Response:
    {
        "success": true,
        "seed_text": "## Background\\n...\\n## Key actors\\n...",
        "sources": [{"url": "...", "title": "..."}],
        "scraped_count": 7,
        "char_count": 4231
    }
    """
    from ..services.firecrawl_service import FirecrawlService
    from ..services.serper_service import SerperService
    from ..services.jina_service import JinaService
    from ..utils.llm_client import LLMClient

    data = request.get_json() or {}
    topic = (data.get("topic") or "").strip()
    extra_urls = data.get("extra_urls", []) or []
    mode = data.get("mode", "policy")  # "policy" or "product"

    if not topic:
        return jsonify({"error": "topic is required"}), 400

    fc = FirecrawlService()
    serper = SerperService()
    jina = JinaService()

    scraped = []

    # 4 sources (not 6): the seed endpoint scrapes live pages serially, so each
    # extra page adds real wall-clock and bloats the synthesis prompt. 4 keeps the
    # briefing well-grounded while staying under the frontend timeout.
    import time as _time
    _t0 = _time.time()

    # Step 1+2 (preferred): Jina search+scrape in one call — more generous free tier.
    # Jina's search endpoint rejects long queries with 422, so truncate to a sane
    # length for the search call. The full topic is still used downstream for synthesis.
    jina_query = topic if len(topic) <= 200 else topic[:200].rsplit(" ", 1)[0]
    if jina.api_key:
        try:
            combined = jina.search_and_scrape(jina_query, num_results=4)
            if combined.get("success"):
                for item in combined.get("scraped_content", []):
                    if item.get("content"):
                        scraped.append({
                            "url": item["url"],
                            "title": item.get("title", ""),
                            "content": item["content"][:3000],
                        })
        except Exception as e:
            logger.warning(f"Jina search_and_scrape failed: {e}")

    # Step 1+2 (fallback): Serper search + Firecrawl scrape — fires when Jina
    # returned nothing OR when Jina was unavailable OR when Jina was bypassed.
    if not scraped and (serper.is_available() or fc.is_available()):
        try:
            combined = serper.search_and_scrape(jina_query if len(topic) > 200 else topic, num_results=4)
            if combined.get("success"):
                for item in combined.get("scraped_content", []):
                    if item.get("content"):
                        scraped.append({
                            "url": item["url"],
                            "title": item.get("title", ""),
                            "content": item["content"][:3000],
                        })
        except Exception as e:
            logger.warning(f"Serper+Firecrawl search failed: {e}")

    # Also scrape any user-supplied URLs (Jina first, Firecrawl fallback)
    for url in extra_urls[:3]:
        r = jina.scrape(url) if jina.api_key else {"success": False}
        if not r.get("success") and fc.is_available():
            try:
                r = fc.scrape(url)
            except Exception as e:
                logger.warning(f"Firecrawl scrape failed for {url}: {e}")
                continue
        if r.get("success"):
            scraped.append({
                "url": url,
                "title": r.get("title", url),
                "content": (r.get("content") or "")[:3000],
            })

    logger.info(f"Seed scrape done: {len(scraped)} sources in {_time.time() - _t0:.1f}s (topic={topic[:60]})")

    if not scraped:
        return jsonify({
            "success": False,
            "error": (
                "No content could be scraped. "
                "Check that FIRECRAWL_API_KEY is valid and (optionally) SERPER_API_KEY is set "
                "for Google search. You can also pass extra_urls explicitly."
            ),
        }), 502

    # Step 3: Synthesize into a structured briefing
    _t_syn = _time.time()
    sources_blob = "\n\n".join(
        f"### Source {i+1}: {s['title']}\n{s['content']}"
        for i, s in enumerate(scraped)
    )
    citations = ", ".join(f"[{i+1}]" for i in range(len(scraped)))

    # Shared "Key figures" section — real numbers that GROUND the scenario the
    # personas react to (prices, incomes, costs, market sizes, adoption rates).
    # Framed hard as CONTEXT to reason against, never lines to recite and never
    # a forecast: the sim must not turn these into a "% who would buy" verdict.
    key_figures_section = (
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

    if mode == "product":
        synthesis_prompt = (
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
    else:
        synthesis_prompt = (
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

    llm = LLMClient()
    system_msg = (
        "You are a research analyst specializing in South African contexts. "
        "Produce concise, fact-grounded briefings. "
        + ("For product simulations, prioritize SA market context; foreign competitors are reference only."
           if mode == "product" else
           "For policy simulations, focus on SA socio-political dynamics.")
    )

    # Append source list to bottom of seed text for transparency.
    sources_md = "\n\n---\n\n## Sources\n" + "\n".join(
        f"[{i+1}] [{s['title'] or s['url']}]({s['url']})"
        for i, s in enumerate(scraped)
    )

    # Synthesis is factored into a callable so the advisory judge can regenerate
    # ONCE on a low score. The retry hint is qualitative only — it must not invite
    # invented facts (the "no invented facts" criterion still applies on the retry).
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
        from ..services.judge_service import judge_enabled, get_judge_service, judge_best_of
        if judge_enabled():
            svc = get_judge_service()
            seed_text, judge_result, regenerated = judge_best_of(
                generate=generate_briefing,
                judge=lambda t: svc.judge_seed_briefing(t, mode, topic),
            )
            if regenerated:
                logger.info(f"Seed briefing regenerated once on judge feedback (topic={topic})")
        else:
            seed_text = generate_briefing()
    except Exception as e:
        logger.error(f"Synthesis LLM call failed: {e}")
        return jsonify({"success": False, "error": f"Synthesis failed: {e}"}), 500

    logger.info(
        f"Seed synthesis done in {_time.time() - _t_syn:.1f}s "
        f"(total {_time.time() - _t0:.1f}s, {len(seed_text)} chars)"
    )

    return jsonify({
        "success": True,
        "seed_text": seed_text,
        "sources": [{"url": s["url"], "title": s["title"]} for s in scraped],
        "scraped_count": len(scraped),
        "char_count": len(seed_text),
        "judge": judge_result.to_dict() if judge_result else None,
    })


@research_bp.route("/people", methods=["POST"])
def search_people():
    """
    Generate ready-to-use agent personas for a described group of people.

    Lets a user type a real-world group (e.g. "Cape Town minibus taxi drivers")
    and get back structured personas they can drop straight into the custom-agent
    roster, to model how that group would react to an event/policy.

    Request body:
    {
        "group": "Cape Town minibus taxi drivers",   // required
        "count": 5,                                    // optional, default 5, max 12
        "ground_with_web": true,                       // optional, default false
        "context": "reaction to SANDF deployment"      // optional extra framing
    }

    Response:
    {
        "success": true,
        "agents": [ {persona dict matching CustomAgentParser shape}, ... ],
        "grounded": true,
        "sources": [{"url": "...", "title": "..."}]
    }
    """
    from ..utils.llm_client import LLMClient

    data = request.get_json() or {}
    group = (data.get("group") or "").strip()
    context = (data.get("context") or "").strip()
    ground_with_web = bool(data.get("ground_with_web", False))

    if not group:
        return jsonify({"error": "group is required"}), 400

    try:
        count = int(data.get("count", 5))
    except (ValueError, TypeError):
        count = 5
    count = max(1, min(count, 12))

    # ---- Optional web grounding: reuse search+scrape (Jina → Serper+Firecrawl) ----
    grounded = False
    sources = []
    web_context = ""
    if ground_with_web:
        from ..services.firecrawl_service import FirecrawlService
        from ..services.serper_service import SerperService
        from ..services.jina_service import JinaService

        fc = FirecrawlService()
        serper = SerperService()
        jina = JinaService()
        scraped = []
        search_query = f"{group} South Africa lived experience concerns daily life" if not context else f"{group} {context} South Africa"

        try:
            if jina.api_key:
                combined = jina.search_and_scrape(search_query, num_results=5)
                if combined.get("success"):
                    for item in combined.get("scraped_content", []):
                        if item.get("content"):
                            scraped.append({"url": item["url"], "title": item.get("title", ""), "content": item["content"][:2500]})
            if not scraped and serper.is_available() and fc.is_available():
                combined = serper.search_and_scrape(search_query, num_results=5)
                if combined.get("success"):
                    for item in combined.get("scraped_content", []):
                        if item.get("content"):
                            scraped.append({"url": item["url"], "title": item.get("title", ""), "content": item["content"][:2500]})
        except Exception as e:
            logger.warning(f"People-search web grounding failed (continuing LLM-only): {e}")

        if scraped:
            sources = [{"url": s["url"], "title": s["title"]} for s in scraped]
            web_context = "\n\n".join(
                f"### Source {i+1}: {s['title']}\n{s['content']}" for i, s in enumerate(scraped)
            )

    # ---- Bind web research to SA people-type segments BEFORE generating personas ----
    # Raw web text is never handed to the persona LLM directly: it goes through
    # _extract_people_type_spec first, so foreign products/brands (the WeWALK leak)
    # stay context and can't define who a persona is. Personas must then conform to
    # one of these distilled SA segments. If extraction yields nothing usable, we
    # fall back to ungrounded generation rather than leaking raw web text through.
    people_type_segments = []
    if web_context:
        people_type_segments = _extract_people_type_spec(web_context, group, context)
        grounded = bool(people_type_segments)

    # ---- Generate personas in the CustomAgentParser dict shape ----
    grounding_block = (
        f"\n\nThese are the REAL SOUTH AFRICAN people-type segments derived from web research "
        f"about this group. Each persona you generate MUST map to one of these segments and stay "
        f"true to it. Set each persona's \"segment\" field to the segment label it represents. "
        f"Do NOT invent person-types outside this list, and never turn a product/brand into a person:\n"
        f"{_format_people_type_spec(people_type_segments)}\n"
        if people_type_segments else ""
    )
    context_block = f"\nThey are being modelled for their reaction to: {context}\n" if context else ""

    prompt = f"""Generate {count} distinct, realistic agent personas representing members of this group:

GROUP: {group}{context_block}{grounding_block}

The personas should capture the genuine diversity *within* this group — different ages, economic
situations, attitudes, and temperaments — not {count} copies of a stereotype. Ground them in real
South African socio-economic context.

For each persona produce a JSON object with these fields:
- name: realistic full name
- persona: 2-4 sentences on who they are, worldview, role
- background_story: 1-2 paragraphs of life history
- age: integer
- gender: "male", "female", or "other"
- education, occupation, country, province, residence, religion, race
- mbti: e.g. "ISTP"
- skills: array of strings
- personality_traits: string
- group_affiliation, behavioral_tendencies, voice_guide
- actor_archetype: one of [civic_moderate, political_activist, violent_agitator, opportunist_looter, mob_follower, conspiracy_spreader, community_leader, institutional_loyalist, disillusioned_dropout, criminal_opportunist, community_protector, grant_dependent_survivor, economic_migrant, whistleblower]
- is_institutional: true/false
- income: string e.g. "R8,000/month"
- emotions: object with keys sadness, joy, fear, disgust, anger, surprise (each 0-10)
- emotion_keyword, emotion_thought
- attitudes: array of {{"topic": "...", "rating": 0-10, "description": "..."}}
- beliefs: array of strings
- segment: the people-type segment label this persona maps to (only when segments are provided above; omit otherwise)

Return ONLY a valid JSON object of the form {{"personas": [ ... ]}}. No explanation."""

    # Generate personas. Factored into a callable so the advisory judge can
    # regenerate ONCE on a low score (judge_best_of). `prev_judge` carries the
    # first attempt's qualitative reasoning back as a hint on the retry — used to
    # improve voice/diversity/realism only. It must NEVER instruct affordability
    # or budget figures; those are computed downstream from real persona data.
    llm = LLMClient()

    def generate_personas(prev_judge=None):
        retry_hint = ""
        if prev_judge is not None and prev_judge.reasoning:
            retry_hint = (
                f"\n\nA previous attempt scored low. Improve on this feedback "
                f"(qualitative only — do NOT change or invent income/budget numbers):\n"
                f"{prev_judge.reasoning}\n"
            )
        parsed = llm.chat_json(
            messages=[
                {"role": "system", "content": "You are an expert in South African socio-economics who designs realistic, diverse agent personas. Return ONLY valid JSON."},
                {"role": "user", "content": prompt + retry_hint},
            ],
            temperature=0.7,
            max_tokens=4000,
        )
        if isinstance(parsed, dict):
            out = parsed.get("personas", parsed.get("agents", parsed.get("profiles", [])))
        elif isinstance(parsed, list):
            out = parsed
        else:
            out = []
        out = [a for a in out if isinstance(a, dict) and a.get("name")]
        for a in out:
            a["source_entity_type"] = "custom_people_search"
        return out

    judge_result = None
    try:
        from ..services.judge_service import judge_enabled, get_judge_service, judge_best_of
        if judge_enabled():
            svc = get_judge_service()
            agents, judge_result, regenerated = judge_best_of(
                generate=generate_personas,
                judge=lambda a: svc.judge_personas(a, topic=group),
            )
            if regenerated:
                logger.info(f"Personas regenerated once on judge feedback (group={group})")
        else:
            agents = generate_personas()
    except Exception as e:
        logger.error(f"People-search persona generation failed: {e}")
        return jsonify({"success": False, "error": f"Persona generation failed: {e}"}), 500

    if not agents:
        return jsonify({"success": False, "error": "No personas were generated. Try rephrasing the group."}), 502

    return jsonify({
        "success": True,
        "group": group,
        "agents": agents,
        "grounded": grounded,
        "sources": sources,
        "count": len(agents),
        "judge": judge_result.to_dict() if judge_result else None,
    })


@research_bp.route("/agents/enrich", methods=["POST"])
def enrich_agent():
    """
    Enrich a partial agent dict — fill in missing/thin fields with the LLM.

    Lets users seed an agent with just a name (or name + a few traits) and
    have the system flesh it out to a full persona, optionally grounded in
    live web research.

    Request body:
    {
        "agent": { "name": "...", ...partial agent dict... },   // required
        "ground_with_web": false                                  // optional
    }

    Response:
    {
        "success": true,
        "agent": { ...fully populated dict, preserving user-provided values... },
        "grounded": false,
        "sources": []
    }

    Behaviour:
    - Existing non-empty fields in `agent` are preserved exactly.
    - Missing or empty fields get LLM-generated values consistent with the
      provided ones (a "taxi driver from Mitchells Plain" stays that).
    - With ground_with_web=true, the LLM is given live web context about
      the role/group/place before generating.
    """
    from ..utils.llm_client import LLMClient

    data = request.get_json() or {}
    agent_in = data.get("agent")
    if not isinstance(agent_in, dict) or not agent_in.get("name"):
        return jsonify({"success": False, "error": "agent.name is required"}), 400
    ground_with_web = bool(data.get("ground_with_web", False))

    # Build a short label describing this person for the web-research query.
    occupation = (agent_in.get("occupation") or "").strip()
    province = (agent_in.get("province") or "").strip()
    archetype = (agent_in.get("actor_archetype") or "").strip()
    name = agent_in["name"]
    descriptor_bits = [b for b in [occupation, province, archetype.replace("_", " ")] if b]
    descriptor = ", ".join(descriptor_bits) if descriptor_bits else name

    # ---- Optional web grounding (same pattern as search_people) ----
    grounded = False
    sources = []
    web_context = ""
    if ground_with_web and descriptor_bits:
        from ..services.firecrawl_service import FirecrawlService
        from ..services.serper_service import SerperService
        from ..services.jina_service import JinaService

        fc = FirecrawlService()
        serper = SerperService()
        jina = JinaService()
        scraped = []
        search_query = f"{descriptor} South Africa lived experience daily life"
        try:
            if jina.api_key:
                combined = jina.search_and_scrape(search_query, num_results=4)
                if combined.get("success"):
                    for item in combined.get("scraped_content", []):
                        if item.get("content"):
                            scraped.append({"url": item["url"], "title": item.get("title", ""), "content": item["content"][:2000]})
            if not scraped and serper.is_available() and fc.is_available():
                combined = serper.search_and_scrape(search_query, num_results=4)
                if combined.get("success"):
                    for item in combined.get("scraped_content", []):
                        if item.get("content"):
                            scraped.append({"url": item["url"], "title": item.get("title", ""), "content": item["content"][:2000]})
        except Exception as e:
            logger.warning(f"Enrich agent web grounding failed (continuing LLM-only): {e}")
        if scraped:
            sources = [{"url": s["url"], "title": s["title"]} for s in scraped]
            web_context = "\n\n".join(
                f"### Source {i+1}: {s['title']}\n{s['content']}" for i, s in enumerate(scraped)
            )

    # Bind web research to SA people-type segments before enriching: raw web text
    # never reaches the persona LLM directly, so foreign products/brands can't
    # redefine who this person is. The persona is constrained to fit whichever
    # segment best matches the descriptor.
    people_type_segments = []
    if web_context:
        people_type_segments = _extract_people_type_spec(web_context, descriptor, "")
        grounded = bool(people_type_segments)

    grounding_block = (
        f"\n\nThese REAL SOUTH AFRICAN people-type segments were derived from web research "
        f"about this kind of person. Keep the persona true to whichever segment best fits the "
        f"fields the user provided. Do NOT pull in foreign products/brands as identity — they are "
        f"context only:\n{_format_people_type_spec(people_type_segments)}\n"
        if people_type_segments else ""
    )

    # Show the LLM only the fields the user actually provided, so it preserves them.
    existing_dump = json.dumps(
        {k: v for k, v in agent_in.items() if v not in (None, "", [], {})},
        ensure_ascii=False, indent=2,
    )

    prompt = f"""You are enriching a partial South African agent persona for a policy simulation.

The user has provided the following fields. PRESERVE THEM EXACTLY:
{existing_dump}

Fill in every other missing field consistently with what the user provided.
If the user said the agent is a taxi driver from the Western Cape, the
background_story / persona / beliefs must reflect THAT specific person —
not a generic one.{grounding_block}

Return a complete JSON object with these fields (preserve provided values verbatim,
generate the missing ones):
- name (provided — preserve verbatim)
- persona: 2-4 sentences on who they are, worldview, role
- background_story: 1-2 paragraphs of life history
- age: integer
- gender: "male", "female", or "other"
- education, occupation, country, province, residence, religion, race
- mbti: e.g. "ISTP"
- skills: array of strings
- personality_traits: string
- group_affiliation, behavioral_tendencies, voice_guide
- actor_archetype: one of [civic_moderate, political_activist, violent_agitator, opportunist_looter, mob_follower, conspiracy_spreader, community_leader, institutional_loyalist, disillusioned_dropout, criminal_opportunist, community_protector, grant_dependent_survivor, economic_migrant, whistleblower]
- is_institutional: true/false
- income: string e.g. "R8,000/month"
- emotions: object with keys sadness, joy, fear, disgust, anger, surprise (each 0-10)
- emotion_keyword, emotion_thought
- attitudes: array of {{"topic": "...", "rating": 0-10, "description": "..."}}
- beliefs: array of strings

Return ONLY a valid JSON object (the agent itself, not wrapped in an array). No explanation."""

    try:
        llm = LLMClient()
        parsed = llm.chat_json(
            messages=[
                {"role": "system", "content": "You are an expert in South African socio-economics who enriches agent personas. Return ONLY valid JSON for one agent."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            max_tokens=2500,
        )
    except Exception as e:
        logger.error(f"Agent enrichment LLM failed: {e}")
        return jsonify({"success": False, "error": f"Enrichment failed: {e}"}), 500

    if not isinstance(parsed, dict):
        return jsonify({"success": False, "error": "LLM did not return a usable persona object."}), 502

    # Merge: user-provided non-empty values win; LLM fills only the rest.
    enriched = dict(parsed)
    for k, v in agent_in.items():
        if v not in (None, "", [], {}):
            enriched[k] = v
    # Always preserve the original _id so the frontend can update in place.
    if agent_in.get("_id"):
        enriched["_id"] = agent_in["_id"]
    if not enriched.get("source_entity_type", "").startswith("custom"):
        enriched["source_entity_type"] = "custom_enriched"

    return jsonify({
        "success": True,
        "agent": enriched,
        "grounded": grounded,
        "sources": sources,
    })


@research_bp.route("/deep", methods=["POST"])
def deep_research():
    """
    Run deep web research for persona enrichment using Firecrawl + Jina + LLM.

    Researches current reality for each archetype found in the document,
    returning structured data that grounds persona generation in real-world conditions.

    Request body:
    {
        "query": "How will minimum wage increase affect informal workers?",
        "document_text": "...content of uploaded PDF...",
        "archetypes": ["informal_trader", "unemployed_youth"]  // optional — auto-detected if omitted
    }

    Response:
    {
        "success": true,
        "enrichment": {
            "informal_trader": "Current wholesale prices up 18%...",
            "unemployed_youth": "60% unemployment, NEET stats...",
            ...
        },
        "archetypes_researched": 4,
        "archetypes_completed": 3,
        "status": "completed"
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body required"}), 400

    query = data.get("query", "").strip()
    document_text = data.get("document_text", "")
    archetypes = data.get("archetypes", [])
    mode = (data.get("mode") or "policy").strip().lower()

    if not isinstance(archetypes, list):
        return jsonify({"error": "archetypes must be a list"}), 400

    # Cap to 3 archetypes for speed (each takes ~2 min of web research)
    archetypes = archetypes[:3]

    # Auto-detect archetypes from document text if not provided
    if not archetypes and document_text:
        archetypes = _detect_archetypes_from_document(document_text, query, mode)
        if not archetypes:
            return jsonify({
                "error": "Could not detect archetypes from document. Please provide archetypes manually."
            }), 400
        # Cap to 3 archetypes for speed (each takes ~2 min of web research)
        archetypes = archetypes[:3]
        logger.info(f"Auto-detected {len(archetypes)} archetypes from document: {archetypes}")

    if not archetypes:
        return jsonify({"error": "At least one archetype is required (provide archetypes or document_text)"}), 400

    if not _is_available():
        return jsonify({
            "error": "Deep research not available. Set FIRECRAWL_API_KEY or JINA_API_KEY in .env"
        }), 503

    try:
        from ..services.deep_research_service import research_archetypes

        logger.info(f"Deep research starting: {len(archetypes)} archetypes for query: {query[:80]}...")

        results = research_archetypes(
            archetypes=archetypes,
            query=query,
            document_text=document_text,
            breadth=3,
            depth=2,
        )

        enrichment = {}
        completed_count = 0

        for archetype, content in results.items():
            if content:
                enrichment[archetype] = content
                completed_count += 1
                logger.info(f"Enrichment data captured for {archetype} ({len(content)} chars)")

        status = "completed" if completed_count == len(archetypes) else "partial"
        if completed_count == 0:
            status = "failed"

        logger.info(f"Deep research {status}: {completed_count}/{len(archetypes)} archetypes enriched")

        return jsonify({
            "success": status != "failed",
            "enrichment": enrichment,
            "archetypes_researched": len(archetypes),
            "archetypes_completed": completed_count,
            "status": status
        })

    except Exception as e:
        logger.error(f"Deep research failed: {e}")
        return jsonify({"error": str(e)}), 500


def _detect_archetypes_from_document(document_text: str, query: str = "", mode: str = "policy") -> list:
    """
    Use the LLM to detect actor archetypes from the seed document — the document
    is the source of truth for who is in the cast. We deliberately do NOT keyword-
    guess archetypes from the text: substring matching on generic words ("crime",
    "reform") pulled SECURITY/policy actors (e.g. SAPS) into product sims that had
    no link to policing. If the LLM can't infer a cast, we fall back to a single
    neutral, mode-appropriate set rather than guessing institutions.
    """
    from ..config import Config
    from openai import OpenAI

    client = OpenAI(api_key=Config.LLM_API_KEY, base_url=Config.LLM_BASE_URL)
    model = Config.LLM_MODEL_NAME

    is_product = mode == "product"

    # Product sims model a market (customers/users/competitors), never the policy/
    # security cast — so those taxonomy lines are omitted from the product prompt.
    if is_product:
        taxonomy = """CUSTOMERS/USERS: civic_moderate, unemployed_youth, gig_worker, student_activist
ECONOMIC: informal_trader, small_business_owner, spaza_shop_owner, taxi_operator
PROFESSIONAL: nurse_healthcare_worker, teacher, community_journalist, ngo_worker
COMMUNITY: community_leader, community_organizer
VULNERABLE: foreign_national, person_with_disability, elderly_grant_recipient, grant_dependent_survivor"""
        intent = "These archetypes are the customer/user types for a product simulation."
    else:
        taxonomy = """CIVIC/ESTABLISHMENT: civic_moderate, community_leader, institutional_loyalist
ACTIVISM: political_activist, student_activist
COMMUNITY: street_committee_chair, traditional_authority, community_organizer, spaza_shop_owner
ECONOMIC: taxi_operator, informal_trader, small_business_owner, gig_worker, unemployed_youth
CRIMINAL/GANG: gang_member, syndicates, mob_follower, opportunist_looter, violent_agitator, criminal_opportunist, community_protector
VULNERABLE: gbv_advocate, foreign_national, person_with_disability, elderly_grant_recipient, grant_dependent_survivor
DISENGAGED: disillusioned_dropout, conspiracy_spreader, whistleblower
PROFESSIONAL: nurse_healthcare_worker, teacher, community_journalist, ngo_worker
SECURITY: police_officer, soldier, private_security, park_ranger"""
        intent = "These archetypes will be used to research current real-world conditions for a policy simulation."

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
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert in South African socio-economics. Return ONLY a JSON array of archetype strings."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=200,
        )
        content = response.choices[0].message.content.strip()
        import json
        result = json.loads(content)
        if isinstance(result, list):
            archetypes = [str(a).strip() for a in result if str(a).strip()]
            if archetypes:
                return archetypes
        elif isinstance(result, dict):
            for key in ["archetypes", "actors", "types"]:
                if key in result and isinstance(result[key], list):
                    archetypes = [str(a).strip() for a in result[key] if str(a).strip()]
                    if archetypes:
                        return archetypes
    except Exception as e:
        logger.warning(f"Archetype LLM detection failed: {e}")

    # Neutral fallback only — used when the LLM call fails or returns nothing, so a
    # run is never killed. No keyword/topic guessing: it must not invent a cast the
    # seed document doesn't support (this is what leaked SAPS into product sims).
    fallback = (
        ["civic_moderate", "small_business_owner", "unemployed_youth"]
        if is_product
        else ["civic_moderate", "community_leader", "unemployed_youth"]
    )
    logger.info(f"Archetype detection fell back to neutral {mode} cast: {fallback}")
    return fallback


# ============================================================================
# Persona Library — browse cached/generated personas in the UI side panel
# ============================================================================

_PERSONA_CACHE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "uploads", "persona_cache"
)


def _persona_cache_dir() -> str:
    os.makedirs(_PERSONA_CACHE_DIR, exist_ok=True)
    return _PERSONA_CACHE_DIR


@research_bp.route("/personas", methods=["GET"])
def list_personas():
    """List every cached persona — metadata only, for the side-panel list.

    Response:
    {
        "success": true,
        "count": 42,
        "personas": [
            { "id": "<hash>", "name": "...", "archetype": "...", "age": 52,
              "occupation": "...", "province": "...", "level": "exact|archetype" },
            ...
        ]
    }
    """
    import json as _json
    d = _persona_cache_dir()
    personas = []
    try:
        # Two persona sources feed this endpoint:
        #   1. The runtime cache (uploads/persona_cache/) — LLM-generated,
        #      no fee-band data, level "exact"/"archetype"
        #   2. The offline library (backend/app/data/persona_library/personas.json)
        #      — survey-grounded, GHS-attached fee-band data, level "library"
        # The Cast picker needs BOTH: cache personas for free-form picks,
        # library personas for the fee-status groups. Merge them with the
        # cache winning on (name, archetype) so a user-edited cache entry
        # overrides the library version. Library fills fee data onto cache
        # entries that lack it.
        lib_index: Dict[Tuple[str, str], Dict] = {}
        try:
            # Source the library via the shared loader so it uses the seeded
            # volume copy on hosts (PERSONA_LIBRARY_PATH), not a baked-in path.
            from ..services.persona_library import get_library
            for lp in get_library().all():
                name = (lp.get("name") or "").strip()
                arch = (lp.get("actor_archetype") or "").strip()
                if name and arch:
                    lib_index[(name, arch)] = lp
        except Exception as e:
            logger.warning(f"Persona library load failed: {e}")

        # 1) Read every library persona — they're real, selectable personas
        #    and the only source of fee-band data. Use the library's stable
        #    `id` directly so the panel segments' `members` list (which uses
        #    the same IDs) lines up with `pickedIds` on the frontend.
        for lp in lib_index.values():
            personas.append({
                "id":         lp.get("id") or (lp.get("name") or "")[:32],
                "name":       lp.get("name") or "Unknown",
                "archetype":  lp.get("actor_archetype") or "",
                "age":        lp.get("age"),
                "gender":     lp.get("gender"),
                "occupation": lp.get("occupation"),
                "province":   lp.get("province"),
                "fees_band":         lp.get("fees_band"),
                "learner_fee_bands": lp.get("learner_fee_bands") or [],
                "level":      "library",
            })

        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(d, fn), "r", encoding="utf-8") as f:
                    data = _json.load(f)
            except Exception:
                continue
            profile = data.get("profile") if isinstance(data, dict) else None
            if not isinstance(profile, dict):
                continue
            meta = data.get("meta", {}) if isinstance(data, dict) else {}
            name = profile.get("name") or meta.get("entity") or "Unknown"
            archetype = profile.get("actor_archetype") or meta.get("type") or ""

            # Fee-band enrichment from the offline library. Cache wins if it
            # already has data; library fills the gap.
            fees_band = profile.get("fees_band")
            learner_fee_bands = profile.get("learner_fee_bands") or []
            if (fees_band is None and not learner_fee_bands):
                lib_match = lib_index.get((name.strip(), archetype.strip()))
                if lib_match:
                    fees_band = lib_match.get("fees_band")
                    learner_fee_bands = lib_match.get("learner_fee_bands") or []

            personas.append({
                "id":         fn[:-5],  # drop .json
                "name":       name,
                "archetype":  archetype,
                "age":        profile.get("age"),
                "gender":     profile.get("gender"),
                "occupation": profile.get("occupation"),
                "province":   profile.get("province"),
                # Fee-band data is the signal the Cast picker needs to drive the
                # "Fee-paying" / "No-fee-school" quick-select groups. Surfaced
                # here (not on the full-profile fetch) so the picker can match
                # personas without an N-call waterfall.
                "fees_band":         fees_band,
                "learner_fee_bands": learner_fee_bands,
                "level":      meta.get("level", "exact"),
            })
        # De-dupe: each persona is stored under two keys (exact + archetype) so
        # the same agent appears twice. Collapse by (name, archetype, occupation)
        # and keep the 'exact' entry when both exist.
        seen = {}
        for p in personas:
            key = (p["name"], p["archetype"], p["occupation"])
            if key not in seen or seen[key]["level"] == "archetype":
                seen[key] = p
        unique = list(seen.values())
        unique.sort(key=lambda x: (x["archetype"] or "", x["name"] or ""))
        return jsonify({"success": True, "count": len(unique), "personas": unique})
    except Exception as e:
        logger.error(f"List personas failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/personas/<persona_id>", methods=["GET"])
def get_persona(persona_id: str):
    """Return one persona's full JSON profile plus the rendered markdown card.

    Response:
    {
        "success": true,
        "profile":  {...full persona dict...},
        "markdown": "# Name\\n\\n**Archetype:** ...",
        "meta":     {...}
    }

    Resolves both:
    - cache personas (`uploads/persona_cache/<hex>.json`)
    - library personas (`backend/app/data/persona_library/personas.json`)
      by their stable library id (same id the list endpoint and the
      panel segment members list expose).
    """
    import json as _json
    # Guard against path traversal — only allow hex hash filenames
    if not persona_id or any(c not in "0123456789abcdef" for c in persona_id.lower()):
        return jsonify({"success": False, "error": "Invalid persona id"}), 400

    # 1) Cache first (faster, has rendered markdown sidecar).
    d = _persona_cache_dir()
    json_path = os.path.join(d, f"{persona_id}.json")
    md_path = os.path.join(d, f"{persona_id}.md")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = _json.load(f)
            markdown = ""
            if os.path.exists(md_path):
                with open(md_path, "r", encoding="utf-8") as f:
                    markdown = f.read()
            return jsonify({
                "success":  True,
                "profile":  data.get("profile", data) if isinstance(data, dict) else {},
                "meta":     data.get("meta", {}) if isinstance(data, dict) else {},
                "markdown": markdown,
            })
        except Exception as e:
            logger.error(f"Get persona {persona_id[:12]} failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    # 2) Library fallback — survey-grounded personas. Wrap in the cache
    #    shape so the frontend's getPersona() consumer doesn't branch.
    try:
        from ..services.persona_library import get_library
        lp = get_library().get(persona_id)
        if lp:
            return jsonify({
                "success":  True,
                "profile":  lp,
                "meta":     {"level": "library", "entity": lp.get("name"), "type": lp.get("actor_archetype")},
                "markdown": "",  # library personas don't have a rendered sidecar
            })
    except Exception as e:
        logger.error(f"Library lookup for persona {persona_id[:12]} failed: {e}")

    return jsonify({"success": False, "error": "Persona not found"}), 404


# ============================================================================
# Project-scoped saved papers — feed literature into sim enrichment
# ============================================================================

def _paper_id(p: dict) -> str:
    """Stable id for de-dup. Prefer the search id, else fall back to URL/title."""
    return str(p.get("id") or p.get("url") or p.get("title") or "").strip()


def _slim_paper(p: dict) -> dict:
    """Keep only the fields we care about when storing on a project."""
    return {
        "id":       _paper_id(p),
        "title":    p.get("title", ""),
        "authors":  p.get("authors", []) if isinstance(p.get("authors"), list) else [str(p.get("authors", ""))],
        "year":     p.get("year"),
        "source":   p.get("source", ""),
        "abstract": p.get("abstract", ""),
        "url":      p.get("url", ""),
    }


@research_bp.route("/projects", methods=["GET"])
def list_projects_for_research():
    """List existing projects so the research page can pick which one to save into."""
    try:
        from ..models.project import ProjectManager
        projects = ProjectManager.list_projects() or []
        out = [{
            "project_id": p.project_id,
            "name":       p.name or "Unnamed Project",
            "updated_at": p.updated_at,
            "papers_count": len(getattr(p, "saved_papers", []) or []),
        } for p in projects]
        # Newest first
        out.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return jsonify({"success": True, "count": len(out), "projects": out})
    except Exception as e:
        logger.error(f"List projects (research) failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/projects/<project_id>/papers", methods=["GET"])
def list_saved_papers(project_id: str):
    """Return the papers currently saved to this project."""
    try:
        from ..models.project import ProjectManager
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({"success": False, "error": "Project not found"}), 404
        papers = list(getattr(project, "saved_papers", []) or [])
        return jsonify({"success": True, "count": len(papers), "papers": papers})
    except Exception as e:
        logger.error(f"List saved papers failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/projects/<project_id>/papers", methods=["POST"])
def save_paper_to_project(project_id: str):
    """Save (or replace) a paper on this project. De-dupes by paper id."""
    try:
        from ..models.project import ProjectManager
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({"success": False, "error": "Project not found"}), 404
        data = request.get_json() or {}
        if not data.get("title") and not data.get("id"):
            return jsonify({"success": False, "error": "Paper must have a title or id"}), 400
        slim = _slim_paper(data)
        pid = slim["id"]
        existing = list(getattr(project, "saved_papers", []) or [])
        # Replace if same id, else append
        existing = [p for p in existing if _paper_id(p) != pid]
        existing.append(slim)
        project.saved_papers = existing
        ProjectManager.save_project(project)
        return jsonify({"success": True, "count": len(existing), "paper": slim})
    except Exception as e:
        logger.error(f"Save paper to project {project_id} failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/projects/<project_id>/papers/<paper_id>", methods=["DELETE"])
def remove_saved_paper(project_id: str, paper_id: str):
    """Remove a saved paper from a project (paper_id matches saved id)."""
    try:
        from ..models.project import ProjectManager
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({"success": False, "error": "Project not found"}), 404
        before = list(getattr(project, "saved_papers", []) or [])
        after  = [p for p in before if _paper_id(p) != paper_id]
        project.saved_papers = after
        ProjectManager.save_project(project)
        return jsonify({"success": True, "removed": len(before) - len(after), "count": len(after)})
    except Exception as e:
        logger.error(f"Remove saved paper failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500