"""Sci-Hub source - grey literature repository.

WARNING: This source may not comply with publisher terms of service.
See docs/fulltext-migration-notes.md for compliance considerations.
"""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from knowcran.paper_fetch.downloader import SourceBase

logger = logging.getLogger(__name__)


class SciHubSource(SourceBase):
    name = "Sci-Hub"
    priority = 90
    is_grey = True
    timeout = 30

    # Known Sci-Hub mirrors (may change frequently)
    _MIRRORS = [
        "https://sci-hub.se",
        "https://sci-hub.st",
        "https://sci-hub.ru",
    ]

    def fetch(self, doi: str | None, arxiv_id: str | None,
              title: str | None = None) -> tuple[bytes | None, str | None]:
        identifier = doi or arxiv_id
        if not identifier:
            return None, "No DOI or arXiv ID"

        for mirror in self._MIRRORS:
            try:
                result = self._try_mirror(mirror, identifier)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"Sci-Hub mirror {mirror} failed: {e}")
                continue
        return None, "All Sci-Hub mirrors failed"

    def _try_mirror(self, mirror: str, identifier: str) -> tuple[bytes | None, str | None]:
        """Try a single Sci-Hub mirror."""
        # Search for paper
        search_url = f"{mirror}/{identifier}"
        resp = requests.get(search_url, timeout=self.timeout,
                            headers={"User-Agent": "KnowCran/1.1"})
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}"

        # Parse response for PDF embed/link
        soup = BeautifulSoup(resp.text, "html.parser")

        # Look for iframe or embed with PDF
        iframe = soup.find("iframe", src=True)
        if iframe:
            pdf_url = iframe.get("src", "")
            if not pdf_url.startswith("http"):
                pdf_url = f"https:{pdf_url}" if pdf_url.startswith("//") else f"{mirror}{pdf_url}"
            pdf_resp = requests.get(pdf_url, timeout=self.timeout,
                                    allow_redirects=True,
                                    headers={"User-Agent": "KnowCran/1.1"})
            if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1024:
                return pdf_resp.content, None

        # Look for embed tag
        embed = soup.find("embed", src=True)
        if embed:
            pdf_url = embed.get("src", "")
            if not pdf_url.startswith("http"):
                pdf_url = f"https:{pdf_url}" if pdf_url.startswith("//") else f"{mirror}{pdf_url}"
            pdf_resp = requests.get(pdf_url, timeout=self.timeout,
                                    allow_redirects=True,
                                    headers={"User-Agent": "KnowCran/1.1"})
            if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1024:
                return pdf_resp.content, None

        # Look for direct download button
        button = soup.find("button", onclick=True)
        if button:
            onclick = button.get("onclick", "")
            url_match = re.search(r"location\.href='([^']+)'", onclick)
            if url_match:
                pdf_url = url_match.group(1)
                if not pdf_url.startswith("http"):
                    pdf_url = f"{mirror}{pdf_url}"
                pdf_resp = requests.get(pdf_url, timeout=self.timeout,
                                        allow_redirects=True,
                                        headers={"User-Agent": "KnowCran/1.1"})
                if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1024:
                    return pdf_resp.content, None

        return None, "No PDF found on mirror"
