"""
Literature Search Service — Multiple academic API integration.

Supports:
- ArXiv (preprints)
- OpenAlex (academic works)
- CrossRef (DOI-based metadata)
- Local uploads (user's own papers)
"""

import urllib.request
import urllib.parse
import urllib.error
import ssl
import xml.etree.ElementTree as ET
import json
import time
import os
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("fub.literature")

# Create SSL context that doesn't verify certificates (for machines without proper CA certs)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


@dataclass
class Paper:
    id: str
    title: str
    authors: List[str]
    year: Optional[int]
    abstract: str
    source: str
    url: str
    citations: Optional[int] = None
    doi: Optional[str] = None
    local_path: Optional[str] = None


class LiteratureSearchService:
    ARXIV_API_URL = "http://export.arxiv.org/api/query"
    OPENALEX_API_URL = "https://api.openalex.org/works"
    CROSSREF_API_URL = "https://api.crossref.org/works"

    def __init__(self, max_results_per_source: int = 10):
        self.max_results = max_results_per_source
        self._local_papers: List[Paper] = []
        self._load_local_papers()

    def _get_local_papers_dir(self) -> Path:
        """Get the directory for storing local papers."""
        upload_dir = os.environ.get('UPLOAD_DIR', 'backend/uploads')
        base_dir = Path(upload_dir)
        papers_dir = base_dir / "research" / "papers"
        papers_dir.mkdir(parents=True, exist_ok=True)
        return papers_dir

    def _load_local_papers(self):
        """Load metadata of locally stored papers."""
        papers_dir = self._get_local_papers_dir()
        metadata_file = papers_dir / "papers.json"

        if metadata_file.exists():
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._local_papers = [
                        Paper(**paper) for paper in data.get("papers", [])
                    ]
                logger.info(f"Loaded {len(self._local_papers)} local papers")
            except Exception as e:
                logger.warning(f"Failed to load local papers metadata: {e}")

    def _save_local_papers_metadata(self):
        """Save metadata of local papers."""
        papers_dir = self._get_local_papers_dir()
        metadata_file = papers_dir / "papers.json"

        try:
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "papers": [asdict(p) for p in self._local_papers]
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save local papers metadata: {e}")

    def search(self, query: str, sources: List[str] = None) -> Dict[str, Any]:
        """
        Search literature across configured sources.

        Args:
            query: Search query string
            sources: List of sources to search ['arxiv', 'openalex', 'crossref', 'local']. If None, searches all.

        Returns:
            Dict with 'papers' list and 'total' count
        """
        if sources is None:
            sources = ["arxiv", "openalex", "crossref", "local"]

        all_papers = []
        source_counts = {}

        if "arxiv" in sources:
            arxiv_papers = self._search_arxiv(query)
            all_papers.extend(arxiv_papers)
            source_counts["arxiv"] = len(arxiv_papers)

        if "openalex" in sources:
            openalex_papers = self._search_openalex(query)
            all_papers.extend(openalex_papers)
            source_counts["openalex"] = len(openalex_papers)

        if "crossref" in sources:
            crossref_papers = self._search_crossref(query)
            all_papers.extend(crossref_papers)
            source_counts["crossref"] = len(crossref_papers)

        if "local" in sources:
            local_papers = self._search_local(query)
            all_papers.extend(local_papers)
            source_counts["local"] = len(local_papers)

        logger.info(f"Literature search for '{query}' returned {len(all_papers)} papers")

        return {
            "papers": [asdict(p) for p in all_papers],
            "total": len(all_papers),
            "by_source": source_counts,
            "query": query
        }

    def add_local_paper(self, title: str, authors: List[str], year: Optional[int],
                        abstract: str, doi: str = None, file_path: str = None) -> Paper:
        """Add a local paper to the collection."""
        paper_id = f"local_{len(self._local_papers) + 1}_{int(time.time())}"

        paper = Paper(
            id=paper_id,
            title=title,
            authors=authors,
            year=year,
            abstract=abstract,
            source="local",
            url=doi or file_path or "",
            doi=doi,
            local_path=file_path
        )

        self._local_papers.append(paper)
        self._save_local_papers_metadata()

        logger.info(f"Added local paper: {title}")
        return paper

    def get_local_papers(self) -> List[Dict[str, Any]]:
        """Get all local papers."""
        return [asdict(p) for p in self._local_papers]

    def _search_local(self, query: str) -> List[Paper]:
        """Search local papers by title or abstract."""
        if not self._local_papers:
            return []

        query_lower = query.lower()
        results = []

        for paper in self._local_papers:
            title_match = query_lower in paper.title.lower()
            abstract_match = query_lower in paper.abstract.lower()
            author_match = any(query_lower in author.lower() for author in paper.authors)

            if title_match or abstract_match or author_match:
                results.append(paper)

        return results

    def _search_arxiv(self, query: str) -> List[Paper]:
        """Search ArXiv API for papers."""
        try:
            params = urllib.parse.urlencode({
                "search_query": f"all:{query}",
                "max_results": self.max_results,
                "sortBy": "relevance",
                "sortOrder": "descending"
            })

            url = f"{self.ARXIV_API_URL}?{params}"
            logger.info(f"ArXiv request URL: {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "Fub-PolicySim/1.0"})

            with urllib.request.urlopen(req, timeout=60, context=ssl_context) as response:
                data = response.read().decode("utf-8")

            return self._parse_arxiv_response(data)

        except urllib.error.HTTPError as e:
            logger.error(f"ArXiv HTTP error {e.code}: {e.reason}")
            return []
        except Exception as e:
            logger.error(f"ArXiv search failed: {e}")
            return []

    def _parse_arxiv_response(self, xml_data: str) -> List[Paper]:
        """Parse ArXiv Atom XML response into Paper objects."""
        papers = []
        try:
            root = ET.fromstring(xml_data)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "arxiv": "http://arxiv.org/schemas/atom"
            }

            for entry in root.findall("atom:entry", ns):
                try:
                    title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
                    abstract = entry.find("atom:summary", ns).text.strip().replace("\n", " ")
                    paper_id = entry.find("atom:id", ns).text.strip()

                    authors = [
                        a.find("atom:name", ns).text
                        for a in entry.findall("atom:author", ns)
                        if a.find("atom:name", ns) is not None
                    ]

                    published_elem = entry.find("atom:published", ns)
                    year = None
                    if published_elem is not None and published_elem.text:
                        year = int(published_elem.text[:4])

                    pdf_link = None
                    for link in entry.findall("atom:link", ns):
                        if link.get("title") == "pdf":
                            pdf_link = link.get("href")
                            break

                    papers.append(Paper(
                        id=paper_id,
                        title=title,
                        authors=authors,
                        year=year,
                        abstract=abstract,
                        source="arxiv",
                        url=pdf_link or paper_id,
                        citations=None
                    ))
                except Exception as e:
                    logger.warning(f"Failed to parse ArXiv entry: {e}")
                    continue

        except ET.ParseError as e:
            logger.error(f"Failed to parse ArXiv XML: {e}")

        time.sleep(3)
        return papers

    def _search_openalex(self, query: str) -> List[Paper]:
        """Search OpenAlex API for papers."""
        try:
            params = urllib.parse.urlencode({
                "search": query,
                "per_page": self.max_results,
                "sort": "relevance_score"
            })

            url = f"{self.OPENALEX_API_URL}?{params}"
            logger.info(f"OpenAlex request URL: {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "Fub-PolicySim/1.0 (mailto:research@fub.ai)"})

            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))

            return self._parse_openalex_response(data)

        except urllib.error.HTTPError as e:
            logger.error(f"OpenAlex HTTP error {e.code}: {e.reason}")
            try:
                error_body = e.read().decode("utf-8")
                logger.error(f"OpenAlex error body: {error_body[:500]}")
            except:
                pass
            return []
        except Exception as e:
            logger.error(f"OpenAlex search failed: {e}")
            return []

    def _parse_openalex_response(self, json_data: Dict) -> List[Paper]:
        """Parse OpenAlex JSON response into Paper objects."""
        papers = []

        try:
            results = json_data.get("results", [])

            for work in results:
                try:
                    title = work.get("title", "")
                    if not title:
                        continue

                    authors = [
                        a.get("author", {}).get("display_name", "Unknown")
                        for a in work.get("authorships", [])
                    ]

                    year = work.get("publication_year")

                    abstract_inverted = work.get("abstract_inverted_index")
                    abstract = ""
                    if abstract_inverted:
                        words = []
                        for word, positions in abstract_inverted.items():
                            for pos in positions:
                                words.append((pos, word))
                        words.sort(key=lambda x: x[0])
                        abstract = " ".join([w[1] for w in words])

                    paper_id = work.get("id", "").replace("https://openalex.org/", "")
                    doi = work.get("doi")

                    pdf_url = None
                    if work.get("open_access"):
                        pdf_url = work["open_access"].get("oa_url")

                    papers.append(Paper(
                        id=paper_id,
                        title=title,
                        authors=authors,
                        year=year,
                        abstract=abstract,
                        source="openalex",
                        url=pdf_url or work.get("doi", paper_id),
                        citations=work.get("cited_by_count"),
                        doi=doi
                    ))
                except Exception as e:
                    logger.warning(f"Failed to parse OpenAlex entry: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to parse OpenAlex response: {e}")

        return papers

    def _search_crossref(self, query: str) -> List[Paper]:
        """Search CrossRef API for papers."""
        try:
            params = urllib.parse.urlencode({
                "query": query,
                "rows": self.max_results,
                "sort": "relevance"
            })

            url = f"{self.CROSSREF_API_URL}?{params}"
            logger.info(f"CrossRef request URL: {url}")
            req = urllib.request.Request(url, headers={
                "User-Agent": "Fub-PolicySim/1.0 (mailto:research@fub.ai)"
            })

            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))

            return self._parse_crossref_response(data)

        except urllib.error.HTTPError as e:
            logger.error(f"CrossRef HTTP error {e.code}: {e.reason}")
            return []
        except Exception as e:
            logger.error(f"CrossRef search failed: {e}")
            return []

    def _parse_crossref_response(self, json_data: Dict) -> List[Paper]:
        """Parse CrossRef JSON response into Paper objects."""
        papers = []

        try:
            items = json_data.get("message", {}).get("items", [])

            for item in items:
                try:
                    title_list = item.get("title", [])
                    title = title_list[0] if title_list else ""
                    if not title:
                        continue

                    authors = [
                        a.get("given", "") + " " + a.get("family", "")
                        for a in item.get("author", [])
                    ]

                    year = None
                    date_parts = item.get("published-print", {}) or item.get("published-online", {}) or item.get("created", {})
                    if date_parts:
                        date_parts = date_parts.get("date-parts", [[]])
                        if date_parts and date_parts[0]:
                            year = date_parts[0][0]

                    abstract = item.get("abstract", "")

                    paper_id = str(item.get("DOI", item.get("URL", "")))

                    doi = item.get("DOI")

                    url = item.get("URL") or f"https://doi.org/{doi}" if doi else ""

                    papers.append(Paper(
                        id=paper_id,
                        title=title,
                        authors=authors,
                        year=year,
                        abstract=abstract,
                        source="crossref",
                        url=url,
                        citations=item.get("is-referenced-by-count"),
                        doi=doi
                    ))
                except Exception as e:
                    logger.warning(f"Failed to parse CrossRef entry: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to parse CrossRef response: {e}")

        return papers