"""DOAJ (Directory of Open Access Journals) source."""

from __future__ import annotations

import logging

import requests

from knowcran.paper_fetch.downloader import SourceBase

logger = logging.getLogger(__name__)


class DOAJSource(SourceBase):
    name = "DOAJ"
    priority = 50
    timeout = 30

    _SEARCH_URL = "https://doaj.org/api/search/articles/doi:{doi}"

    def fetch(self, doi: str | None, arxiv_id: str | None,
              title: str | None = None, pmid: str | None = None) -> tuple[bytes | None, str | None]:
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
                bibjson = result.get("bibjson", {})
                fulltext = bibjson.get("fulltext", {})
                pdf_url = fulltext.get("url")
                if pdf_url:
                    pdf_resp = requests.get(pdf_url, timeout=self.timeout,
                                            allow_redirects=True,
                                            headers={"User-Agent": "KnowCran/1.1"})
                    if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1024:
                        return pdf_resp.content, None
            return None, "No fulltext URL found"
        except requests.RequestException as e:
            return None, str(e)
