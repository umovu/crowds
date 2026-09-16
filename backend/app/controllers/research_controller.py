"""Literature search, web research and papers saved against a project.

  POST   /api/research/search                          search every configured source
  POST   /api/research/search/<source>                 search one source
  GET    /api/research/local                           locally stored papers
  POST   /api/research/local                           add a paper by hand
  POST   /api/research/local/upload                    upload a paper file
  POST   /api/research/web                             research a query, or scrape a URL
  POST   /api/research/web/scrape                      scrape one page
  GET    /api/research/web/status                      what is configured
  POST   /api/research/web/search                      Google via Serper
  POST   /api/research/enrich                          research -> agent prompt context
  POST   /api/research/seed                            build a seed briefing
  POST   /api/research/deep                            deep research per archetype
  GET    /api/research/projects                        projects to save papers into
  GET    /api/research/projects/<id>/papers            papers saved on a project
  POST   /api/research/projects/<id>/papers            save a paper
  DELETE /api/research/projects/<id>/papers/<paper_id> remove a saved paper

The work lives in research_service and seed_service. This file reads the request and
turns the answer into JSON. A service that is not configured raises ServiceUnavailable,
which becomes a 503 here.
"""

import os

from flask import jsonify, request

from . import research_bp
from ..repositories import project_repository
from ..services import research_service, seed_service
from ..services.research_service import ServiceUnavailable
from ..utils.logger import get_logger

logger = get_logger("fub.controller.research")

LITERATURE_SOURCES = ("arxiv", "openalex", "crossref", "local")


def _body():
    """The JSON body, or None when there isn't one."""
    return request.get_json(silent=True)


# ── literature search ───────────────────────────────────────────────────────────
@research_bp.route("/search", methods=["POST"])
def search_literature():
    """Search academic literature across all configured sources."""
    data = _body()
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
        results = research_service.search(query, sources, max_results)
        logger.info(f"Literature search: query='{query}', sources={sources}, "
                    f"results={results['total']}")
        return jsonify(results)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Literature search failed: {e}")
        return jsonify({"error": str(e)}), 500


@research_bp.route("/search/<source>", methods=["POST"])
def search_source_only(source):
    """Search only a specific source (arxiv, openalex, crossref, local)."""
    if source not in LITERATURE_SOURCES:
        return jsonify({"error": f"Unknown source: {source}"}), 400

    data = _body()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        return jsonify(research_service.search(
            query, sources=[source], max_results=data.get("max_results", 10)))
    except Exception as e:  # noqa: BLE001
        logger.error(f"{source} search failed: {e}")
        return jsonify({"error": str(e)}), 500


# ── local papers ────────────────────────────────────────────────────────────────
@research_bp.route("/local", methods=["GET"])
def get_local_papers():
    """Get all locally uploaded papers."""
    try:
        papers = research_service.local_papers()
        return jsonify({"papers": papers, "total": len(papers)})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get local papers: {e}")
        return jsonify({"error": str(e)}), 500


@research_bp.route("/local", methods=["POST"])
def add_local_paper():
    """Add a local paper manually (without file upload)."""
    data = _body()
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

    try:
        paper = research_service.add_paper(
            title=title, authors=authors, year=year,
            abstract=data.get("abstract", ""), doi=data.get("doi"))
        return jsonify({"success": True, "paper": {
            "id": paper.id, "title": paper.title, "authors": paper.authors,
            "year": paper.year, "source": paper.source,
        }}), 201
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to add local paper: {e}")
        return jsonify({"error": str(e)}), 500


@research_bp.route("/local/upload", methods=["POST"])
def upload_local_paper():
    """Upload a local paper file (PDF, MD, or TXT) with optional metadata."""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in research_service.ALLOWED_PAPER_EXTENSIONS:
        allowed = ', '.join(research_service.ALLOWED_PAPER_EXTENSIONS)
        return jsonify({"error": f"File type not allowed. Allowed: {allowed}"}), 400

    title = request.form.get('title', '').strip() or file.filename
    authors_str = request.form.get('authors', '')
    authors = [a.strip() for a in authors_str.split(',')] if authors_str else []
    year = request.form.get('year')
    year = int(year) if year and year.isdigit() else None

    try:
        # `file.save` is passed in, so the upload object stays in the controller.
        path = research_service.save_uploaded_paper(file.save, title, ext)
        paper = research_service.add_paper(
            title=title, authors=authors, year=year,
            abstract=request.form.get('abstract', ''),
            doi=request.form.get('doi', ''), file_path=path)
        return jsonify({"success": True, "paper": {
            "id": paper.id, "title": paper.title, "authors": paper.authors,
            "year": paper.year, "source": paper.source, "local_path": paper.local_path,
        }}), 201
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to upload paper: {e}")
        return jsonify({"error": str(e)}), 500


# ── web research ────────────────────────────────────────────────────────────────
@research_bp.route("/web", methods=["POST"])
def web_research():
    """Research a query (deep research, then Serper+Firecrawl), or scrape a given URL."""
    data = _body()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    query = data.get("query", "").strip()
    url = data.get("url", "").strip()
    if not query and not url:
        return jsonify({"error": "Query or URL is required"}), 400

    try:
        return jsonify(research_service.web(query, url, data.get("agent_context", {})))
    except ServiceUnavailable as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:  # noqa: BLE001
        logger.error(f"Web research failed: {e}")
        return jsonify({"error": str(e)}), 500


@research_bp.route("/web/scrape", methods=["POST"])
def firecrawl_scrape():
    """Scrape a single webpage using Firecrawl."""
    data = _body()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        return jsonify(research_service.scrape(url))
    except ServiceUnavailable as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:  # noqa: BLE001
        logger.error(f"Firecrawl scrape failed: {e}")
        return jsonify({"error": str(e)}), 500


@research_bp.route("/web/status", methods=["GET"])
def web_research_status():
    """Check availability of web research services."""
    try:
        return jsonify(research_service.availability())
    except Exception as e:  # noqa: BLE001
        return jsonify({"available": False, "error": str(e)}), 500


@research_bp.route("/web/search", methods=["POST"])
def serper_search():
    """Search Google via Serper."""
    data = _body()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        return jsonify(research_service.serper_search(
            query, min(data.get("num_results", 10), 20)))
    except ServiceUnavailable as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:  # noqa: BLE001
        logger.error(f"Serper search failed: {e}")
        return jsonify({"error": str(e)}), 500


# ── enrichment ──────────────────────────────────────────────────────────────────
@research_bp.route("/enrich", methods=["POST"])
def enrich_agents():
    """Turn research findings into enriched context for agent prompts."""
    data = _body()
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
        context = research_service.enrich(
            query, archetypes, research_type,
            papers=data.get("papers", []), urls=data.get("urls", []))
        return jsonify({
            "success": True, "query": query, "research_type": research_type,
            "archetypes": archetypes, "context": context,
            "enriched_count": len(context),
        })
    except research_service.UnknownResearchType as e:
        return jsonify({"error": str(e)}), 400
    except ServiceUnavailable as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:  # noqa: BLE001
        logger.error(f"Agent enrichment failed: {e}")
        return jsonify({"error": str(e)}), 500


# ── seed briefing ───────────────────────────────────────────────────────────────
@research_bp.route("/seed", methods=["POST"])
def generate_seed():
    """Build a seed briefing from live web research, for users with no document."""
    data = _body() or {}
    topic = (data.get("topic") or "").strip()
    if not topic:
        return jsonify({"error": "topic is required"}), 400

    try:
        seed = seed_service.generate(
            topic, mode=data.get("mode", "policy"),
            extra_urls=data.get("extra_urls", []) or [])
    except seed_service.NoSources as e:
        return jsonify({"success": False, "error": str(e)}), 502
    except seed_service.SynthesisFailed as e:
        return jsonify({"success": False, "error": f"Synthesis failed: {e}"}), 500

    return jsonify({
        "success": True,
        "seed_text": seed.seed_text,
        "sources": seed.sources,
        "scraped_count": seed.scraped_count,
        "char_count": seed.char_count,
        "judge": seed.judge,
    })


# ── deep research ───────────────────────────────────────────────────────────────
@research_bp.route("/deep", methods=["POST"])
def deep_research():
    """Run deep web research per archetype, to ground personas in current conditions."""
    data = _body()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    archetypes = data.get("archetypes", [])
    if not isinstance(archetypes, list):
        return jsonify({"error": "archetypes must be a list"}), 400

    try:
        return jsonify(research_service.deep(
            query=data.get("query", "").strip(),
            document_text=data.get("document_text", ""),
            archetypes=archetypes,
            mode=(data.get("mode") or "policy").strip().lower()))
    except research_service.NoArchetypes as e:
        return jsonify({"error": str(e)}), 400
    except ServiceUnavailable as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:  # noqa: BLE001
        logger.error(f"Deep research failed: {e}")
        return jsonify({"error": str(e)}), 500


# ── papers saved on a project ───────────────────────────────────────────────────
@research_bp.route("/projects", methods=["GET"])
def list_projects_for_research():
    """List existing projects so the research page can pick which one to save into."""
    try:
        projects = project_repository.list_projects() or []
        out = [{
            "project_id": p.project_id,
            "name": p.name or "Unnamed Project",
            "updated_at": p.updated_at,
            "papers_count": len(getattr(p, "saved_papers", []) or []),
        } for p in projects]
        out.sort(key=lambda x: x.get("updated_at") or "", reverse=True)  # newest first
        return jsonify({"success": True, "count": len(out), "projects": out})
    except Exception as e:  # noqa: BLE001
        logger.error(f"List projects (research) failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/projects/<project_id>/papers", methods=["GET"])
def list_saved_papers(project_id: str):
    """Return the papers currently saved to this project."""
    try:
        project = project_repository.get(project_id)
        if not project:
            return jsonify({"success": False, "error": "Project not found"}), 404
        papers = list(getattr(project, "saved_papers", []) or [])
        return jsonify({"success": True, "count": len(papers), "papers": papers})
    except Exception as e:  # noqa: BLE001
        logger.error(f"List saved papers failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/projects/<project_id>/papers", methods=["POST"])
def save_paper_to_project(project_id: str):
    """Save (or replace) a paper on this project. De-dupes by paper id."""
    try:
        project = project_repository.get(project_id)
        if not project:
            return jsonify({"success": False, "error": "Project not found"}), 404

        data = _body() or {}
        if not data.get("title") and not data.get("id"):
            return jsonify({"success": False,
                            "error": "Paper must have a title or id"}), 400

        slim = research_service.slim_paper(data)
        existing = [p for p in (getattr(project, "saved_papers", []) or [])
                    if research_service.paper_id(p) != slim["id"]]
        existing.append(slim)
        project.saved_papers = existing
        project_repository.save(project)
        return jsonify({"success": True, "count": len(existing), "paper": slim})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Save paper to project {project_id} failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@research_bp.route("/projects/<project_id>/papers/<paper_id>", methods=["DELETE"])
def remove_saved_paper(project_id: str, paper_id: str):
    """Remove a saved paper from a project (paper_id matches saved id)."""
    try:
        project = project_repository.get(project_id)
        if not project:
            return jsonify({"success": False, "error": "Project not found"}), 404
        before = list(getattr(project, "saved_papers", []) or [])
        after = [p for p in before if research_service.paper_id(p) != paper_id]
        project.saved_papers = after
        project_repository.save(project)
        return jsonify({"success": True, "removed": len(before) - len(after),
                        "count": len(after)})
    except Exception as e:  # noqa: BLE001
        logger.error(f"Remove saved paper failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
