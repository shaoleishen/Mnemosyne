"""Europe PMC source - full text XML/PDF lookup."""

from __future__ import annotations

import logging
import re

import requests

from knowcran.paper_fetch.downloader import SourceBase

logger = logging.getLogger(__name__)


class EuropePMCSource(SourceBase):
    name = "EuropePMC"
    priority = 35
    timeout = 30

    _SEARCH_URL = "https://europepmc.org/search?query=DOI:{doi}&format=json"

    def fetch(self, doi: str | None, arxiv_id: str | None,
              title: str | None = None) -> tuple[bytes | None, str | None]:
        if not doi:
            return None, "No DOI"
        try:
            resp = requests.get(self._SEARCH_URL.format(doi=doi),
                                timeout=self.timeout,
                                headers={"User-Agent": "KnowCran/1.1"})
            if resp.status_code != 200:
                return None, f"Search returned {resp.status_code}"
            data = resp.json()
            results = data.get("resultList", {}).get("result", [])
            for result in results:
                pmcid = result.get("pmcid")
                if pmcid:
                    # Try to get PDF from PMC
                    pdf_url = f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf"
                    pdf_resp = requests.get(pdf_url, timeout=self.timeout,
                                            allow_redirects=True,
                                            headers={"User-Agent": "KnowCran/1.1"})
                    if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1024:
                        return pdf_resp.content, None
            return None, "No PMC PDF found"
        except requests.RequestException as e:
            return None, str(e)
