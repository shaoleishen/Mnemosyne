"""CORE source - open access research papers."""

from __future__ import annotations

import logging

import requests

from knowcran.paper_fetch.downloader import SourceBase

logger = logging.getLogger(__name__)


class CORESource(SourceBase):
    name = "CORE"
    priority = 45
    timeout = 30

    _SEARCH_URL = "https://api.core.ac.uk/v3/search/works?q=doi:{doi}"

    def fetch(self, doi: str | None, arxiv_id: str | None,
              title: str | None = None) -> tuple[bytes | None, str | None]:
        if not doi:
            return None, "No DOI"
        try:
            resp = requests.get(self._SEARCH_URL.format(doi=doi),
                                timeout=self.timeout,
                                headers={"User-Agent": "KnowCran/1.1"})
            if resp.status_code != 200:
                return None, f"API returned {resp.status_code}"
            data = resp.json()
            results = data.get("results", [])
            for result in results:
                links = result.get("links", [])
                download_url = result.get("downloadUrl")
                if download_url:
                    pdf_resp = requests.get(download_url, timeout=self.timeout,
                                            allow_redirects=True,
                                            headers={"User-Agent": "KnowCran/1.1"})
                    if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1024:
                        return pdf_resp.content, None
            return None, "No download URL found"
        except requests.RequestException as e:
            return None, str(e)
