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
        "https://sci-hub.st",
        "https://sci-hub.ru",
        "https://sci-hub.se",
    ]

    def fetch(self, doi: str | None, arxiv_id: str | None,
              title: str | None = None, pmid: str | None = None) -> tuple[bytes | None, str | None]:
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
        search_url = f"{mirror}/{identifier}"
        resp = requests.get(search_url, timeout=self.timeout,
                            headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}"

        text = resp.text

        # Quick check: paper not available
        if "article is not available" in text.lower():
            return None, "Not available on Sci-Hub"

        # Parse response for PDF embed/link
        soup = BeautifulSoup(text, "html.parser")

        # Look for <object> tag (current Sci-Hub format)
        obj = soup.find("object", data=True)
        if obj:
            pdf_url = obj.get("data", "")
            if pdf_url:
                result = self._download_pdf(pdf_url, mirror)
                if result:
                    return result

        # Look for <iframe> tag
        iframe = soup.find("iframe", src=True)
        if iframe:
            pdf_url = iframe.get("src", "")
            if pdf_url and pdf_url != "about:blank":
                result = self._download_pdf(pdf_url, mirror)
                if result:
                    return result

        # Look for <embed> tag
        embed = soup.find("embed", src=True)
        if embed:
            pdf_url = embed.get("src", "")
            if pdf_url:
                result = self._download_pdf(pdf_url, mirror)
                if result:
                    return result

        # Look for direct download button
        button = soup.find("button", onclick=True)
        if button:
            onclick = button.get("onclick", "")
            url_match = re.search(r"location\.href='([^']+)'", onclick)
            if url_match:
                pdf_url = url_match.group(1)
                result = self._download_pdf(pdf_url, mirror)
                if result:
                    return result

        # Look for PDF URL in page text (fallback)
        pdf_match = re.search(r'(https?://[^\s"\']+\.pdf(?:#[^\s"\']*)?)', text)
        if pdf_match:
            result = self._download_pdf(pdf_match.group(1), mirror)
            if result:
                return result

        return None, "No PDF found on mirror"

    def _download_pdf(self, url: str, mirror: str) -> tuple[bytes | None, str | None]:
        """Download PDF from a URL, fixing relative/protocol-relative URLs."""
        if url.startswith("//"):
            url = f"https:{url}"
        elif not url.startswith("http"):
            url = f"{mirror}{url}"
        try:
            pdf_resp = requests.get(url, timeout=self.timeout,
                                    allow_redirects=True,
                                    headers={"User-Agent": "Mozilla/5.0"})
            if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1024:
                ct = pdf_resp.headers.get("content-type", "")
                if "pdf" in ct or pdf_resp.content[:4] == b"%PDF":
                    return pdf_resp.content, None
        except requests.RequestException:
            pass
        return None, None
