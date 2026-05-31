"""Direct URL source - downloads PDF from a known URL (e.g., openAccessPdf).

This is used when we already have a direct PDF URL from paper metadata,
such as from Semantic Scholar's openAccessPdf field.
"""

from __future__ import annotations

import logging

import requests

from knowcran.paper_fetch.downloader import SourceBase

logger = logging.getLogger(__name__)


class DirectUrlSource(SourceBase):
    """Download PDF directly from a known URL.

    This source is not registered in the standard source list.
    Instead, it's used explicitly when a paper's openAccessPdf URL is known.
    """
    name = "DirectUrl"
    priority = 5  # Highest priority - direct URL
    timeout = 30

    def __init__(self, url: str):
        self._url = url

    def fetch(self, doi: str | None, arxiv_id: str | None,
              title: str | None = None) -> tuple[bytes | None, str | None]:
        if not self._url:
            return None, "No URL provided"
        try:
            resp = requests.get(
                self._url,
                timeout=self.timeout,
                allow_redirects=True,
                headers={"User-Agent": "KnowCran/1.1"},
            )
            if resp.status_code == 200 and len(resp.content) > 1024:
                # Check content type if available
                ct = resp.headers.get("content-type", "")
                if "pdf" in ct or resp.content[:4] == b"%PDF":
                    return resp.content, None
                # Some servers don't set content-type correctly but serve valid PDFs
                if resp.content[:4] == b"%PDF":
                    return resp.content, None
            return None, f"HTTP {resp.status_code} or not a PDF"
        except requests.RequestException as e:
            return None, str(e)


def try_direct_url(url: str, doi: str | None = None,
                   arxiv_id: str | None = None) -> tuple[bytes | None, str | None]:
    """Try to download a PDF from a direct URL.

    Convenience function for use in download_paper_pdf().
    """
    source = DirectUrlSource(url)
    return source.fetch(doi=doi, arxiv_id=arxiv_id)
