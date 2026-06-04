"""OpenAlex source - open access PDF lookup."""

from __future__ import annotations

import logging

import requests

from knowcran.paper_fetch.downloader import SourceBase

logger = logging.getLogger(__name__)


class OpenAlexSource(SourceBase):
    name = "OpenAlex"
    priority = 25
    timeout = 30

    _API_URL = "https://api.openalex.org/works/doi:{doi}"

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
            # Look for open access PDF
            oa = data.get("open_access", {})
            pdf_url = oa.get("oa_url")
            if pdf_url:
                pdf_resp = requests.get(pdf_url, timeout=self.timeout,
                                        allow_redirects=True,
                                        headers={"User-Agent": "KnowCran/1.1"})
                if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1024:
                    return pdf_resp.content, None
            return None, "No OA PDF URL"
        except requests.RequestException as e:
            return None, str(e)
