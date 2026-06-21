"""
JinaService — web search + scrape via Jina AI Reader.

Two endpoints used:
- r.jina.ai/{url}     → returns clean markdown of any page
- s.jina.ai/{query}   → searches the web and returns top results with markdown content

With JINA_API_KEY: 200 req/min, structured JSON, search endpoint enabled.
Without: rate-limited (~20 req/min), reader still works.

Generally more generous than Firecrawl free tier (unlimited pages, only rate-limited).
"""

import os
import json
import logging
import requests
from typing import Dict, Any, List, Optional
from urllib.parse import quote

logger = logging.getLogger("fub.jina_service")


class JinaService:
    READER_URL = "https://r.jina.ai/"
    SEARCH_URL = "https://s.jina.ai/"

    def __init__(self):
        self.api_key = os.environ.get("JINA_API_KEY", "").strip()

    def is_available(self) -> bool:
        # Reader endpoint works without a key; the service is considered "available"
        # as long as we have network. We always return True here — actual failures
        # are handled per-request.
        return True

    def _headers(self, json_output: bool = True) -> Dict[str, str]:
        h = {}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        if json_output and self.api_key:
            # Accept JSON only if we have a key — anonymous reader returns markdown
            h["Accept"] = "application/json"
        return h

    def scrape(self, url: str, timeout: float = 30.0) -> Dict[str, Any]:
        """Fetch clean markdown content of a single URL via Jina Reader."""
        target = url.lstrip("/")
        try:
            r = requests.get(
                self.READER_URL + target,
                headers=self._headers(json_output=True),
                timeout=timeout,
            )
            r.raise_for_status()

            # With API key: JSON response; without: plain markdown
            content_type = r.headers.get("content-type", "")
            if "json" in content_type:
                data = r.json().get("data", {}) or {}
                return {
                    "success": True,
                    "url": url,
                    "title": data.get("title", "") or "",
                    "content": data.get("content", "") or data.get("text", "") or "",
                    "source": "jina",
                }
            else:
                # Plain markdown
                return {
                    "success": True,
                    "url": url,
                    "title": "",
                    "content": r.text,
                    "source": "jina",
                }
        except requests.HTTPError as e:
            logger.warning(f"Jina reader HTTP {e.response.status_code} for {url}")
            return {"success": False, "error": f"HTTP {e.response.status_code}", "url": url}
        except Exception as e:
            logger.warning(f"Jina reader failed for {url}: {e}")
            return {"success": False, "error": str(e), "url": url}

    def search(self, query: str, num_results: int = 6, timeout: float = 60.0) -> Dict[str, Any]:
        """
        Search the web via Jina's search endpoint.
        Requires JINA_API_KEY. Returns top results with markdown content already
        scraped (combined search + scrape in one call).
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "Jina search requires JINA_API_KEY. Set it in .env",
                "query": query,
            }
        # Jina rejects long queries with 422; also encode '/' so it doesn't become a path segment.
        safe_query = quote(query[:200].strip(), safe="")
        try:
            r = requests.get(
                self.SEARCH_URL + safe_query,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                    "X-Respond-With": "no-content",  # initial probe; we'll fetch content on demand
                },
                timeout=timeout,
            )
            r.raise_for_status()
            data = r.json()
            results = data.get("data", [])[:num_results]
            return {
                "success": True,
                "query": query,
                "results": [
                    {
                        "url": item.get("url", ""),
                        "title": item.get("title", ""),
                        "snippet": item.get("description", "") or item.get("snippet", ""),
                    }
                    for item in results
                ],
                "source": "jina",
            }
        except requests.HTTPError as e:
            logger.warning(f"Jina search HTTP {e.response.status_code} for '{safe_query}'")
            return {"success": False, "error": f"HTTP {e.response.status_code}", "query": safe_query}
        except Exception as e:
            logger.warning(f"Jina search failed for '{safe_query}': {e}")
            return {"success": False, "error": str(e), "query": safe_query}

    def search_and_scrape(self, query: str, num_results: int = 6, timeout: float = 90.0) -> Dict[str, Any]:
        """
        Search the web and return scraped markdown content for each top result.
        Combined search + scrape — replaces serper+firecrawl with one call.
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "Jina search_and_scrape requires JINA_API_KEY",
                "query": query,
            }
        # Jina rejects long queries with 422; also encode '/' so it doesn't become a path segment.
        safe_query = quote(query[:200].strip(), safe="")
        try:
            r = requests.get(
                self.SEARCH_URL + safe_query,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                },
                timeout=timeout,
            )
            r.raise_for_status()
            data = r.json()
            results = data.get("data", [])[:num_results]
            scraped = []
            for item in results:
                content = item.get("content", "") or item.get("text", "") or ""
                if content:
                    scraped.append({
                        "url": item.get("url", ""),
                        "title": item.get("title", "") or item.get("url", ""),
                        "content": content[:3000],
                    })
            return {
                "success": True,
                "query": query,
                "scraped_content": scraped,
                "source": "jina",
            }
        except requests.HTTPError as e:
            logger.warning(f"Jina search_and_scrape HTTP {e.response.status_code} for '{safe_query}'")
            return {"success": False, "error": f"HTTP {e.response.status_code}", "query": safe_query}
        except Exception as e:
            logger.warning(f"Jina search_and_scrape failed for '{safe_query}': {e}")
            return {"success": False, "error": str(e), "query": safe_query}
