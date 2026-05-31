"""Unpaywall source - open access PDF lookup via DOI."""

from __future__ import annotations

import logging

import requests

from knowcran.paper_fetch.downloader import SourceBase

logger = logging.getLogger(__name__)


class UnpaywallSource(SourceBase):
    name = "Unpaywall"
    priority = 20
    timeout = 30

    _API_URL = "https://api.unpaywall.org/v2/{doi}?email=knowcran@example.com"

    def fetch(self, doi: str | None, arxiv_id: str | None,
              title: str | None = None) -> tuple[bytes | None, str | None]:
        if not doi:
            return None, "No DOI"
        api_url = self._API_URL.format(doi=doi)
        try:
            resp = requests.get(api_url, timeout=self.timeout,
                                headers={"User-Agent": "KnowCran/1.1"})
            if resp.status_code != 200:
                return None, f"API returned {resp.status_code}"
            data = resp.json()
            # Try best OA location
            oa = data.get("best_oa_location")
            if oa and oa.get("url_for_pdf"):
                pdf_url = oa["url_for_pdf"]
                pdf_resp = requests.get(pdf_url, timeout=self.timeout,
                                        allow_redirects=True,
                                        headers={"User-Agent": "KnowCran/1.1"})
                if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1024:
                    return pdf_resp.content, None
            return None, "No OA PDF URL found"
        except requests.RequestException as e:
            return None, str(e)
