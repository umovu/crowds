"""
MiroFlow MCP Server — runs alongside Flask backend on port 8001.

Exposes a `run_task` tool that performs multi-step web research:
1. Search the web for relevant sources
2. Scrape and read top results
3. Synthesize findings into a research report

Standalone — does NOT import from app to avoid agentsociety2 dependency.
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

# ── Load .env from project root ────────────────────────────────
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_env_path = os.path.join(_project_root, ".env")
if os.path.exists(_env_path):
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path, override=True)
    except ImportError:
        pass

# ── Configuration ──────────────────────────────────────────────
LLM_API_KEY = os.environ.get("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", os.environ.get("AGENTSOCIETY_LLM_API_KEY", "")))
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", os.environ.get("AGENTSOCIETY_LLM_API_BASE", "http://localhost:11434/v1"))
LLM_MODEL = os.environ.get("LLM_MODEL_NAME", os.environ.get("AGENTSOCIETY_LLM_MODEL", "ollama/mistral"))
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
DEEP_RESEARCH_URL = os.environ.get("DEEP_RESEARCH_URL", "")  # e.g. http://localhost:3051

# ── MCP Server ─────────────────────────────────────────────────
mcp = FastMCP("miroflow-research", port=8001)


async def _web_search(query: str, num_results: int = 5) -> List[Dict[str, str]]:
    """Search the web and return results with snippets."""
    results = []

    # Try Serper first
    if SERPER_API_KEY:
        try:
            import requests
            resp = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": query, "num": num_results},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("organic", []):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                    })
                if results:
                    return results
        except Exception:
            pass

    # Fallback: DuckDuckGo HTML
    try:
        import requests
        from bs4 import BeautifulSoup
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for result in soup.select(".result"):
            title_el = result.select_one(".result__a")
            snippet_el = result.select_one(".result__snippet")
            if title_el and snippet_el:
                results.append({
                    "title": title_el.get_text(strip=True),
                    "url": title_el.get("href", ""),
                    "snippet": snippet_el.get_text(strip=True),
                })
            if len(results) >= num_results:
                break
    except Exception:
        pass

    return results


async def _scrape_url(url: str) -> str:
    """Scrape a URL and return markdown content. Skips PDFs and binary files."""
    # Skip PDF and binary URLs
    url_lower = url.lower()
    if url_lower.endswith('.pdf') or '/pdf/' in url_lower or '.pdf?' in url_lower:
        return ""

    # Try Firecrawl first
    if FIRECRAWL_API_KEY:
        try:
            import requests
            resp = requests.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {FIRECRAWL_API_KEY}"},
                json={"url": url, "formats": ["markdown"]},
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("data", {}).get("markdown", "")
                if content:
                    return content
        except Exception:
            pass

    # Fallback: direct scrape
    try:
        import requests
        from bs4 import BeautifulSoup
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15,
            allow_redirects=True
        )
        resp.raise_for_status()
        # Skip if content-type indicates PDF or binary
        content_type = resp.headers.get('content-type', '').lower()
        if 'pdf' in content_type or 'application/octet-stream' in content_type:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines[:300])
    except Exception:
        return ""


async def _synthesize(query: str, sources: List[Dict[str, str]], llm: str) -> str:
    """Use LLM to synthesize research findings into a report."""
    source_text = ""
    for i, src in enumerate(sources, 1):
        source_text += f"\n--- Source {i}: {src.get('title', 'Untitled')} ---\n"
        source_text += f"URL: {src.get('url', '')}\n"
        source_text += f"Snippet: {src.get('snippet', '')}\n"
        if src.get("content"):
            source_text += f"Content:\n{src['content'][:2000]}\n"

    prompt = f"""You are a research analyst. Synthesize the following web research results into a comprehensive report.

Research query: {query}

Sources found:
{source_text}

Write a detailed research report that includes:
1. Key findings and current data
2. Relevant statistics, dates, and quotes
3. Different perspectives and stakeholder positions
4. Geographic and demographic context
5. Recent events and developments

Be specific, cite sources where possible, and provide actionable insights.
Return the report in plain text (no markdown headers)."""

    # Use synchronous requests to avoid asyncio.TaskGroup issues
    import requests
    try:
        resp = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": llm or LLM_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a research analyst. Write comprehensive reports based on web research."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 4000,
            },
            timeout=60
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        return f"Synthesis failed: {e}"


async def _run_inline(query: str, llm: str = "") -> str:
    """Inline fallback: Serper search + scrape + local LLM synthesis."""
    search_query = query.split("\n")[0].strip()
    for line in query.split("\n"):
        if line.startswith("Research question:"):
            search_query = line.replace("Research question:", "").strip()
            break
    search_query = search_query[:100]

    search_results = await _web_search(search_query, num_results=5)
    if not search_results:
        return f"No web results found for: {search_query}"

    for src in search_results[:3]:
        if src.get("url"):
            content = await _scrape_url(src["url"])
            if content:
                src["content"] = content

    report = await _synthesize(query, search_results, llm)
    return (
        f"## Web Research Results ##\n\nAnswer: {report}\n\n"
        f"## Research Steps ##\n"
        f"1. Searched web for: {search_query}\n"
        f"2. Found {len(search_results)} sources\n"
        f"3. Scraped {sum(1 for s in search_results if s.get('content'))} pages\n"
        f"4. Synthesized report using {llm or LLM_MODEL}"
    )


@mcp.tool()
async def run_task(task_description: str, llm: str = "", agent: str = "") -> str:
    """
    Perform multi-step web research.

    If DEEP_RESEARCH_URL is set, forwards the query to the deep-research API server
    (github.com/dzhng/deep-research) which does iterative deepening research with
    full-page Firecrawl scraping. Falls back to inline Serper+LLM synthesis otherwise.

    Args:
        task_description: The research question or topic to investigate
        llm: LLM model to use for synthesis (optional, uses default)
        agent: Agent configuration (optional, unused)

    Returns:
        Research report with findings, key learnings, and source URLs
    """
    query = task_description.strip()
    if not query:
        return "Error: task_description cannot be empty"

    if not DEEP_RESEARCH_URL:
        return await _run_inline(query, llm)

    import requests
    try:
        resp = requests.post(
            f"{DEEP_RESEARCH_URL}/api/research",
            json={"query": query, "depth": 3, "breadth": 4},
            timeout=180,
        )
        resp.raise_for_status()
        data = resp.json()

        answer = data.get("answer", "")
        learnings = data.get("learnings", [])
        urls = data.get("visitedUrls", [])

        if not answer and not learnings:
            return await _run_inline(query, llm)

        report = answer or ""
        if learnings:
            report += "\n\nKey findings:\n" + "\n".join(f"- {l}" for l in learnings[:15])
        if urls:
            report += "\n\nSources: " + ", ".join(urls[:5])
        return report

    except Exception as e:
        # deep-research unreachable — fall back to inline
        print(f"[mcp] deep-research call failed ({e}), falling back to inline research")
        return await _run_inline(query, llm)


def main():
    """Start the MCP server."""
    print(f"MiroFlow MCP Server starting on port 8001...")
    print(f"  LLM: {LLM_MODEL} @ {LLM_BASE_URL}")
    print(f"  Firecrawl: {'configured' if FIRECRAWL_API_KEY else 'not configured'}")
    print(f"  Serper: {'configured' if SERPER_API_KEY else 'not configured'}")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
