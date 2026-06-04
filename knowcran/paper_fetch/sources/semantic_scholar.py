"""Semantic Scholar source - PDF from openAccessPdf metadata."""

from __future__ import annotations

import json
import logging

import requests

from knowcran.paper_fetch.downloader import SourceBase

logger = logging.getLogger(__name__)


class SemanticScholarSource(SourceBase):
    name = "SemanticScholar"
    priority = 30
    timeout = 30

    _API_URL = "https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=openAccessPdf"

    def fetch(self, doi: str | None, arxiv_id: str | None,
              title: str | None = None, pmid: str | None = None) -> tuple[bytes | None, str | None]:
        if not doi:
            return None, "No DOI"
        api_url = self._API_URL.format(doi=doi)
        try:
            resp = requests.get(api_url, timeout=self.timeout,
                                headers={"User-Agent": "KnowCran/1.1"})
            if resp.status_code != 200:
                return None, f"API returned {resp.status_code}"
            data = resp.json()
            oa = data.get("openAccessPdf")
            if oa and oa.get("url"):
                pdf_resp = requests.get(oa["url"], timeout=self.timeout,
                                        allow_redirects=True,
                                        headers={"User-Agent": "KnowCran/1.1"})
                if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1024:
                    return pdf_resp.content, None
            return None, "No OA PDF URL"
        except requests.RequestException as e:
            return None, str(e)
