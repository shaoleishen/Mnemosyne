"""Crossref source - publisher link lookup via DOI."""

from __future__ import annotations

import logging
import re

import requests

from knowcran.paper_fetch.downloader import SourceBase

logger = logging.getLogger(__name__)


class CrossrefSource(SourceBase):
    name = "Crossref"
    priority = 55
    timeout = 30

    _API_URL = "https://api.crossref.org/works/{doi}"

    def fetch(self, doi: str | None, arxiv_id: str | None,
              title: str | None = None, pmid: str | None = None) -> tuple[bytes | None, str | None]:
        if not doi:
            return None, "No DOI"
        try:
            resp = requests.get(self._API_URL.format(doi=doi),
                                timeout=self.timeout,
                                headers={"User-Agent": "KnowCran/1.1"})
            if resp.status_code != 200:
                return None, f"API returned {resp.status_code}"
            data = resp.json()
            message = data.get("message", {})
            links = message.get("link", [])
            for link in links:
                if link.get("content-type") == "application/pdf":
                    pdf_url = link.get("URL")
                    if pdf_url:
                        pdf_resp = requests.get(pdf_url, timeout=self.timeout,
                                                allow_redirects=True,
                                                headers={"User-Agent": "KnowCran/1.1"})
                        if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1024:
                            return pdf_resp.content, None
            return None, "No PDF link found"
        except requests.RequestException as e:
            return None, str(e)
