"""arXiv PDF source - direct download from arxiv.org."""

from __future__ import annotations

import logging
import re

import requests

from knowcran.paper_fetch.downloader import SourceBase

logger = logging.getLogger(__name__)


class ArxivSource(SourceBase):
    name = "arXiv"
    priority = 10
    timeout = 30

    _PDF_URL = "https://arxiv.org/pdf/{arxiv_id}.pdf"

    def fetch(self, doi: str | None, arxiv_id: str | None,
              title: str | None = None, pmid: str | None = None) -> tuple[bytes | None, str | None]:
        if not arxiv_id:
            return None, "No arXiv ID"
        url = self._PDF_URL.format(arxiv_id=arxiv_id)
        try:
            resp = requests.get(url, timeout=self.timeout, allow_redirects=True,
                                headers={"User-Agent": "KnowCran/1.1"})
            if resp.status_code == 200 and len(resp.content) > 1024:
                return resp.content, None
            return None, f"HTTP {resp.status_code}"
        except requests.RequestException as e:
            return None, str(e)
