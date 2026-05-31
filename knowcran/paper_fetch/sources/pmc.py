"""PubMed Central source - free PDF from PMC."""

from __future__ import annotations

import logging
import re

import requests

from knowcran.paper_fetch.downloader import SourceBase

logger = logging.getLogger(__name__)


class PMCSource(SourceBase):
    name = "PMC"
    priority = 40
    timeout = 30

    _OA_LIST_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmcid}"

    def fetch(self, doi: str | None, arxiv_id: str | None,
              title: str | None = None) -> tuple[bytes | None, str | None]:
        # PMC requires a PMC ID, which we'd need to look up from DOI
        # This is a simplified implementation - in practice would use E-utilities
        if not doi:
            return None, "No DOI"
        try:
            # Use EuropePMC to find PMCID
            search_url = f"https://europepmc.org/search?query=DOI:{doi}&format=json"
            resp = requests.get(search_url, timeout=self.timeout,
                                headers={"User-Agent": "KnowCran/1.1"})
            if resp.status_code != 200:
                return None, f"Search returned {resp.status_code}"
            data = resp.json()
            results = data.get("resultList", {}).get("result", [])
            for result in results:
                pmcid = result.get("pmcid")
                if pmcid:
                    # Try OA service
                    oa_url = self._OA_LIST_URL.format(pmcid=pmcid)
                    oa_resp = requests.get(oa_url, timeout=self.timeout,
                                           headers={"User-Agent": "KnowCran/1.1"})
                    if oa_resp.status_code == 200:
                        # Parse XML for download link
                        text = oa_resp.text
                        match = re.search(r'href="(https://[^"]+\.pdf)"', text)
                        if match:
                            pdf_resp = requests.get(match.group(1), timeout=self.timeout,
                                                    allow_redirects=True,
                                                    headers={"User-Agent": "KnowCran/1.1"})
                            if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1024:
                                return pdf_resp.content, None
            return None, "No PMC PDF found"
        except requests.RequestException as e:
            return None, str(e)
