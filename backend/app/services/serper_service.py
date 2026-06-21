"""
Serper Service — Google Search via Serper API.

Direct Google search capability for Fub. Used alongside Firecrawl
for deep web research.
"""

import requests
from typing import Dict, Any, List, Optional
from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("fub.serper")


class SerperService:
    """Service for performing Google searches via Serper API."""

    SEARCH_URL = "https://google.serper.dev/search"

    def __init__(self):
        self.api_key = Config.SERPER_API_KEY

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, num_results: int = 10) -> Dict[str, Any]:
        """
        Perform a Google search via Serper.

        Args:
            query: Search query
            num_results: Number of results to return (max 20)

        Returns:
            Dict with search results
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "Serper API key not configured. Set SERPER_API_KEY in .env",
                "query": query
            }

        try:
            resp = requests.post(
                self.SEARCH_URL,
                headers={
                    "X-API-KEY": self.api_key,
                    "Content-Type": "application/json"
                },
                json={"q": query, "num": num_results},
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("organic", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "position": item.get("position", 0)
                })

            return {
                "success": True,
                "query": query,
                "results": results,
                "total": len(results),
                "source": "serper"
            }

        except requests.exceptions.HTTPError as e:
            logger.error(f"Serper HTTP error: {e}")
            return {"success": False, "error": str(e), "query": query}
        except Exception as e:
            logger.error(f"Serper search failed: {e}")
            return {"success": False, "error": str(e), "query": query}

    def search_and_scrape(self, query: str, num_results: int = 3) -> Dict[str, Any]:
        """
        Search Google then scrape top results via Firecrawl.

        Args:
            query: Search query
            num_results: Number of search results to scrape

        Returns:
            Dict with combined search + scrape results
        """
        from ..services.firecrawl_service import FirecrawlService

        fc = FirecrawlService()
        if not fc.is_available():
            return self.search(query, num_results)

        search_result = self.search(query, num_results)
        if not search_result.get("success"):
            return search_result

        scraped = []
        for result in search_result.get("results", [])[:num_results]:
            url = result.get("url", "")
            if url:
                scrape_result = fc.scrape(url)
                if scrape_result.get("success"):
                    scraped.append({
                        "url": url,
                        "title": result.get("title", ""),
                        "content": scrape_result.get("content", "")[:3000]
                    })

        return {
            "success": True,
            "query": query,
            "search_results": search_result.get("results", []),
            "scraped_content": scraped,
            "source": "serper+firecrawl"
        }