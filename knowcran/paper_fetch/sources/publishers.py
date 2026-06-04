"""Publisher direct PDF links - tries common publisher URL patterns."""

from __future__ import annotations

import logging
import re

import requests

from knowcran.paper_fetch.downloader import SourceBase

logger = logging.getLogger(__name__)


class PublishersSource(SourceBase):
    name = "Publishers"
    priority = 60
    timeout = 30

    # Common publisher PDF URL patterns
    _PATTERNS = [
        # Elsevier/ScienceDirect
        r"https?://(?:www\.)?sciencedirect\.com/science/article/pii/(\w+)",
        # Springer/Nature
        r"https?://(?:www\.)?(?:nature\.com|springer\.com)/articles/([^\s]+)",
        # Wiley
        r"https?://(?:www\.)?(?:onlinelibrary\.)?wiley\.com/doi/(?:abs|full|pdf)/([^\s]+)",
        # PLOS
        r"https?://(?:www\.)?journals\.plos\.org/[^/]+/article\?id=([^\s]+)",
        # BMJ
        r"https?://(?:www\.)?(?:bmj\.com|bmjopen\.bmj\.com)/content/([^\s]+)",
        # PubMed Central (free)
        r"https?://(?:www\.)?ncbi\.nlm\.nih\.gov/pmc/articles/([^\s]+)",
    ]

    def fetch(self, doi: str | None, arxiv_id: str | None,
              title: str | None = None, pmid: str | None = None) -> tuple[bytes | None, str | None]:
        if not doi:
            return None, "No DOI"
        # Try to resolve DOI to get publisher page
        try:
            resp = requests.head(f"https://doi.org/{doi}", timeout=self.timeout,
                                 allow_redirects=True,
                                 headers={"User-Agent": "KnowCran/1.1"})
            if resp.status_code != 200:
                return None, f"DOI resolution failed: {resp.status_code}"
            url = resp.url
            # Try common PDF URL transformations
            pdf_urls = self._guess_pdf_urls(url)
            for pdf_url in pdf_urls:
                try:
                    pdf_resp = requests.get(pdf_url, timeout=self.timeout,
                                            allow_redirects=True,
                                            headers={"User-Agent": "KnowCran/1.1"})
                    if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1024:
                        ct = pdf_resp.headers.get("content-type", "")
                        if "pdf" in ct or pdf_resp.content[:4] == b"%PDF":
                            return pdf_resp.content, None
                except requests.RequestException:
                    continue
            return None, "No accessible PDF from publisher"
        except requests.RequestException as e:
            return None, str(e)

    def _guess_pdf_urls(self, page_url: str) -> list[str]:
        """Generate candidate PDF URLs from a publisher page URL."""
        urls = []
        # ScienceDirect: add /pdfft
        if "sciencedirect.com" in page_url:
            urls.append(page_url.replace("/article/", "/article/pii/").rstrip("/") + "/pdfft")
        # Nature: append .pdf
        if "nature.com" in page_url:
            urls.append(page_url.rstrip("/") + ".pdf")
        # PLOS: direct PDF link
        if "plos.org" in page_url:
            urls.append(page_url.replace("article?id=", "article/file?id=").rstrip("/") + "&type=printable")
        return urls
