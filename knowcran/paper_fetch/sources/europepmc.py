"""Europe PMC source - full text PDF lookup via EuropePMC."""

from __future__ import annotations

import logging

import requests

from knowcran.paper_fetch.downloader import SourceBase

logger = logging.getLogger(__name__)


class EuropePMCSource(SourceBase):
    name = "EuropePMC"
    priority = 35
    timeout = 30

    _SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={query}&format=json&resultType=core"
    _PDF_RENDER_URL = "https://europepmc.org/articles/{pmcid}?pdf=render"

    def fetch(self, doi: str | None, arxiv_id: str | None,
              title: str | None = None, pmid: str | None = None) -> tuple[bytes | None, str | None]:
        if not doi and not pmid:
            return None, "No DOI or PMID"

        # Try PMID first, then DOI (PMID search may not always work in EuropePMC)
        pmcid, pdf_urls = None, []
        if pmid:
            pmcid, pdf_urls = self._search_europepmc(f"PMID:{pmid}")
        if not pmcid and doi:
            pmcid, pdf_urls = self._search_europepmc(f"DOI:{doi}")

        # Try PDF render URL if we have PMCID
        if pmcid:
            pdf_urls.insert(0, self._PDF_RENDER_URL.format(pmcid=pmcid))

        # Try all PDF URLs
        for pdf_url in pdf_urls:
            try:
                resp = requests.get(pdf_url, timeout=self.timeout,
                                    allow_redirects=True,
                                    headers={"User-Agent": "KnowCran/1.1"})
                if resp.status_code == 200 and len(resp.content) > 1024:
                    ct = resp.headers.get("content-type", "")
                    if "pdf" in ct or resp.content[:4] == b"%PDF":
                        return resp.content, None
            except requests.RequestException:
                continue

        return None, "No PDF found in EuropePMC"

    def _search_europepmc(self, query: str) -> tuple[str | None, list[str]]:
        """Search EuropePMC for PMCID and full text URLs."""
        try:
            url = self._SEARCH_URL.format(query=query)
            resp = requests.get(url, timeout=self.timeout,
                                headers={"User-Agent": "KnowCran/1.1"})
            if resp.status_code != 200:
                return None, []

            data = resp.json()
            results = data.get("resultList", {}).get("result", [])
            for result in results:
                pmcid = result.get("pmcid")
                # Collect PDF URLs from fullTextUrlList
                pdf_urls = []
                ft_list = result.get("fullTextUrlList", {}).get("fullTextUrl", [])
                for ft in ft_list:
                    ft_url = ft.get("url", "")
                    ft_style = ft.get("documentStyle", "")
                    if ft_style == "pdf" or ft_url.endswith(".pdf"):
                        pdf_urls.append(ft_url)

                return pmcid, pdf_urls

            return None, []
        except (requests.RequestException, ValueError) as e:
            logger.debug(f"EuropePMC search failed: {e}")
            return None, []
