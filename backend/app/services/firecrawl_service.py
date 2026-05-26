"""
Firecrawl Service — Direct web scraping via Firecrawl API.

Alternative to MiroFlow for web content retrieval. Used when
MiroFlow MCP server is not available or when simpler scraping is needed.
"""

import requests
from typing import Dict, Any, Optional
from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("fub.firecrawl")


class FirecrawlService:
    """Service for scraping webpages via Firecrawl API."""

    SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"
    SEARCH_URL = "https://api.firecrawl.dev/v1/search"

    def __init__(self):
        self.api_key = Config.FIRECRAWL_API_KEY

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        """Search the web using Firecrawl's search endpoint."""
        if not self.api_key:
            return {
                "success": False,
                "error": "Firecrawl API key not configured. Set FIRECRAWL_API_KEY in .env",
                "query": query
            }

        try:
            resp = requests.post(
                self.SEARCH_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"query": query, "limit": num_results, "scrapeOptions": {"formats": ["markdown"]}},
                timeout=60
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("data", []):
                results.append({
                    "title": item.get("metadata", {}).get("title", ""),
                    "url": item.get("metadata", {}).get("sourceURL", item.get("url", "")),
                    "snippet": item.get("metadata", {}).get("description", ""),
                    "content": item.get("markdown", "")[:3000],
                })

            return {
                "success": True,
                "query": query,
                "results": results,
                "total": len(results),
                "source": "firecrawl"
            }

        except requests.exceptions.HTTPError as e:
            logger.error(f"Firecrawl search HTTP error: {e}")
            return {"success": False, "error": str(e), "query": query}
        except Exception as e:
            logger.error(f"Firecrawl search failed: {e}")
            return {"success": False, "error": str(e), "query": query}

    def scrape(self, url: str) -> Dict[str, Any]:
        """
        Scrape a webpage and return its markdown content.

        Args:
            url: The URL to scrape
        Returns:
            Dict with success, content, and url
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "Firecrawl API key not configured. Set FIRECRAWL_API_KEY in .env",
                "url": url
            }

        try:
            resp = requests.post(
                self.SCRAPE_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"url": url, "formats": ["markdown"]},
                timeout=120
            )
            resp.raise_for_status()
            data = resp.json()

            markdown = data.get("data", {}).get("markdown", "")
            if not markdown:
                return {
                    "success": False,
                    "error": "No content returned from Firecrawl",
                    "url": url
                }

            return {
                "success": True,
                "content": markdown,
                "url": url,
                "source": "firecrawl"
            }

        except requests.exceptions.HTTPError as e:
            logger.error(f"Firecrawl HTTP error: {e}")
            return {"success": False, "error": str(e), "url": url}
        except Exception as e:
            logger.error(f"Firecrawl scrape failed: {e}")
            return {"success": False, "error": str(e), "url": url}

    def search_and_scrape(self, query: str, num_results: int = 3) -> Dict[str, Any]:
        """
        Placeholder for search + scrape functionality.
        For true web search, use MiroFlow. This method provides
        a simple scrape of a known URL.

        Args:
            query: The research query
            num_results: Not used for direct scraping
        Returns:
            Dict with search_and_scrape results
        """
        return {
            "success": False,
            "error": "Search not available via Firecrawl alone. Use /api/research/search for literature or set up MiroFlow for web search.",
            "query": query
        }