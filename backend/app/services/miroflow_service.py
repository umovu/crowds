"""
MiroFlow Service — Agentsociety2 Web Research via MiroFlow MCP

Wraps agentsociety2.skills.web_research.execute_web_research() for use
in Flask API endpoints. Requires MiroFlow MCP server running externally.
"""

import asyncio
import json
import concurrent.futures
from typing import Dict, Any, Optional, List
from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("fub.miroflow")


class MiroFlowService:
    """Service for performing web research via MiroFlow MCP server."""

    def __init__(self):
        self.api_url = Config.WEB_SEARCH_API_URL
        self.api_token = Config.WEB_SEARCH_API_TOKEN
        self.default_llm = Config.MIROFLOW_DEFAULT_LLM
        self.default_agent = Config.MIROFLOW_DEFAULT_AGENT

    def is_available(self) -> bool:
        """Check if MiroFlow MCP server is configured."""
        return bool(self.api_url)

    async def research(self, query: str) -> Dict[str, Any]:
        """
        Perform multi-step web research via MiroFlow.

        Args:
            query: Research question or topic to investigate

        Returns:
            Dict with research findings
        """
        if not self.is_available():
            return {
                "success": False,
                "content": "MiroFlow MCP server not configured. Set WEB_SEARCH_API_URL in .env",
                "query": query
            }

        try:
            from agentsociety2.skills.web_research import execute_web_research

            result = await execute_web_research(
                query=query,
                llm=self.default_llm,
                agent=self.default_agent
            )

            logger.info(f"MiroFlow research complete for '{query[:50]}...'")
            return self._extract_content(result)

        except ImportError as e:
            logger.error(f"MiroFlow library not available: {e}")
            return {
                "success": False,
                "content": "agentsociety2.web_research module not available. Check installation.",
                "query": query,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"MiroFlow research failed: {e}")
            return {
                "success": False,
                "content": f"Research failed: {str(e)}",
                "query": query,
                "error": str(e)
            }

    def _clean_llm_output(self, content: str) -> str:
        """Remove leaked LLM tokens, PDF binary artifacts, and noise from model output."""
        import re
        if not content:
            return content
        # Remove common leaked tokens
        content = re.sub(r'\*K\s*', '', content)
        content = re.sub(r' +\+ +\+ +\+ +\+.*', '', content)
        content = re.sub(r'assistant<\|header_end\|>', '', content)
        content = re.sub(r'<\|[\w_]+\|>', '', content)
        # Remove PDF/binary artifacts
        content = re.sub(r'%PDF-\d\.\d.*', '', content)
        content = re.sub(r'\d+\s+0\s+obj\s*<<.*?>>\s*endobj', '', content, flags=re.DOTALL)
        content = re.sub(r'/[A-Za-z]+\s*<<.*?>>', '', content, flags=re.DOTALL)
        content = re.sub(r'\[/View\s*/Design\]', '', content)
        # Remove lines that are just binary noise (high non-printable ratio)
        lines = []
        for line in content.split('\n'):
            if line.strip():
                printable = sum(1 for c in line if c.isprintable() or c.isspace())
                if printable / max(len(line), 1) > 0.7:
                    lines.append(line)
        content = '\n'.join(lines)
        # Remove repeated single-char noise patterns
        content = re.sub(r'([^\w\s])\1{5,}', '', content)
        # Clean up resulting whitespace
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content.strip()

    def _extract_content(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract clean content from MiroFlow's response format."""
        if not result.get("success"):
            return result

        raw_content = result.get("content", "")
        if not raw_content:
            return result

        # Detect TaskGroup/async errors masquerading as successful results
        if "unhandled errors" in raw_content.lower() or "taskgroup" in raw_content.lower():
            return {
                "success": False,
                "content": "",
                "query": result.get("query", ""),
                "error": raw_content
            }

        # Try to extract content between "Answer" and next section
        import re
        answer_match = re.search(r'Answer[:\s]*(.*?)(?=##\s|\Z)', raw_content, re.DOTALL)
        if answer_match:
            content = answer_match.group(1).strip()
            if content:
                result["content"] = content
                return result

        # Try to extract from markdown sections
        sections = re.split(r'##\s+', raw_content)
        for section in sections:
            if section.strip().startswith(('Answer', 'Research', 'Findings', 'Summary', 'Results')):
                content = section.strip()
                if content:
                    result["content"] = content
                    return result

        # Fallback: clean up the raw content
        cleaned = re.sub(r'##\s+Miro Web Research \(MCP\) Results\s*##\s*', '', raw_content)
        cleaned = re.sub(r'##\s+Research Steps\s*##.*', '', cleaned, flags=re.DOTALL)
        cleaned = cleaned.strip()
        if cleaned:
            result["content"] = cleaned

        return result

    def research_sync(self, query: str) -> Dict[str, Any]:
        """Synchronous wrapper for research()."""
        return asyncio.run(self.research(query))

    def _build_archetype_query(self, archetype: str, query: str, document_text: str) -> str:
        """Build a focused research prompt for a specific archetype."""
        doc_context = ""
        if document_text:
            doc_context = f"\n\nPolicy context:\n{document_text[:1500]}"

        return f"""Research the current conditions for {archetype} in South Africa{doc_context}.

Research question: {query}

Find current, real-world data on:
1. Economic conditions: wages, costs, employment rates, income sources
2. Recent events: protests, policy changes, crime incidents, strikes, community actions in the last 6-12 months
3. Actual language patterns: quotes from social media, community forums, news interviews — how do these people actually speak?
4. Stakeholder positions: who supports/opposes the policy, why, what are their demands
5. Geographic distribution: which townships, suburbs, provinces are most affected
6. Demographics: age ranges, education levels, household composition
7. Daily pressures: load-shedding impact, water access, transport costs, food prices, healthcare access
8. Historical context: similar policies implemented before, what happened, lessons learned

Return a comprehensive research report with specific numbers, dates, quotes, and sources."""

    def _research_archetype_inline(self, archetype: str, query: str, document_text: str = "") -> Dict[str, Any]:
        """Fallback: synchronous research via direct web search + local LLM synthesis."""
        import requests
        from ..config import Config

        search_query = f"{archetype} South Africa current conditions 2024 2025"
        results = []

        # Search via Serper only
        try:
            from ..services.serper_service import SerperService
            serper = SerperService()
            if serper.is_available():
                serper_result = serper.search(search_query, num_results=5)
                if serper_result.get("success"):
                    for item in serper_result.get("results", []):
                        results.append({
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "snippet": item.get("snippet", ""),
                            "content": "",
                        })
                    logger.info(f"[inline] Serper returned {len(results)} results for {archetype}")
        except Exception as e:
            logger.warning(f"[inline] Serper search failed for {archetype}: {e}")

        if not results:
            return {
                "success": False,
                "content": f"No web results found for {archetype}",
                "archetype": archetype,
                "error": "No search results"
            }

        # Scrape top 2 results
        for src in results[:2]:
            if src.get("url"):
                try:
                    page_resp = requests.get(
                        src["url"],
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                        timeout=15,
                        allow_redirects=True
                    )
                    page_resp.raise_for_status()
                    from bs4 import BeautifulSoup
                    page_soup = BeautifulSoup(page_resp.text, "html.parser")
                    for tag in page_soup(["script", "style", "nav", "footer", "header", "aside"]):
                        tag.decompose()
                    text = page_soup.get_text(separator="\n", strip=True)
                    lines = [line.strip() for line in text.split("\n") if line.strip()]
                    content = "\n".join(lines[:200])
                    if content:
                        src["content"] = content
                except Exception as e:
                    logger.debug(f"[inline] Scrape failed for {src['url']}: {e}")

        # Synthesize with LLM
        source_text = ""
        for i, src in enumerate(results, 1):
            source_text += f"\n--- Source {i}: {src.get('title', 'Untitled')} ---\n"
            source_text += f"URL: {src.get('url', '')}\n"
            source_text += f"Snippet: {src.get('snippet', '')}\n"
            if src.get("content"):
                source_text += f"Content:\n{src['content'][:2000]}\n"

        doc_context = ""
        if document_text:
            doc_context = f"\n\nPolicy context:\n{document_text[:1500]}"

        prompt = f"""Research the current conditions for {archetype} in South Africa{doc_context}.
Research question: {query}

Sources found:
{source_text}

Write a detailed research report that includes:
1. Key findings and current data
2. Relevant statistics, dates, and quotes
3. Different perspectives and stakeholder positions
4. Geographic and demographic context
5. Recent events and developments

Be specific, cite sources where possible, and provide actionable insights."""

        try:
            llm_resp = requests.post(
                f"{Config.LLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {Config.LLM_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": Config.LLM_MODEL_NAME,
                    "messages": [
                        {"role": "system", "content": "You are a research analyst specializing in South African socio-economics."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 4000,
                },
                timeout=60
            )
            llm_resp.raise_for_status()
            data = llm_resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            if content:
                cleaned = self._clean_llm_output(content)
                return {
                    "success": True,
                    "content": cleaned,
                    "archetype": archetype,
                    "source": "inline_local"
                }
        except Exception as e:
            logger.error(f"[inline] LLM synthesis failed for {archetype}: {e}")

        # Fallback: return raw sources
        combined = "\n\n---\n\n".join(
            f"{r['title']}\n{r['snippet']}" + (f"\n\n{r['content'][:1000]}" if r.get("content") else "")
            for r in results if r.get("snippet")
        )
        return {
            "success": True,
            "content": combined,
            "archetype": archetype,
            "source": "raw_sources"
        }

    def research_archetype_sync(self, archetype: str, query: str, document_text: str = "") -> Dict[str, Any]:
        """Synchronous research for a single archetype via MiroFlow MCP server (agentsociety2)."""
        if not self.is_available():
            return {
                "success": False,
                "content": f"MiroFlow MCP server not configured for {archetype}",
                "archetype": archetype,
                "error": "WEB_SEARCH_API_URL not set in .env"
            }

        # Build the full research prompt for this archetype
        prompt = self._build_archetype_query(archetype, query, document_text)

        # Primary path: use agentsociety2 → local MCP server
        try:
            result = self.research_sync(prompt)
            if result.get("success"):
                content = result.get("content", "")
                cleaned = self._clean_llm_output(content)
                return {
                    "success": True,
                    "content": cleaned,
                    "archetype": archetype,
                    "source": "miroflow_mcp"
                }
            else:
                logger.warning(f"MCP research returned error for {archetype}: {result.get('error')}")
        except Exception as e:
            logger.warning(f"MCP research failed for {archetype}, falling back to inline: {e}")

        # Fallback: inline local web search + LLM synthesis
        return self._research_archetype_inline(archetype, query, document_text)

    def research_archetypes_batch(
        self,
        archetypes: List[str],
        query: str,
        document_text: str = "",
        max_workers: int = 3
    ) -> Dict[str, Dict[str, Any]]:
        """
        Research multiple archetypes in parallel.

        Args:
            archetypes: List of archetype names to research
            query: Main research question
            document_text: Policy document content for context
            max_workers: Number of parallel research tasks (default 3)

        Returns:
            Dict mapping archetype → research result
        """
        results = {}

        def research_one(archetype):
            logger.info(f"Starting MiroFlow research for archetype: {archetype}")
            return archetype, self.research_archetype_sync(archetype, query, document_text)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(research_one, arch): arch for arch in archetypes}
            for future in concurrent.futures.as_completed(futures):
                archetype, result = future.result()
                results[archetype] = result
                status = "✓" if result.get("success") else "✗"
                logger.info(f"Research {status} for {archetype}")

        return results