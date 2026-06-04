"""PubMed Central source - free PDF from PMC via NCBI ID Converter."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

import requests

from knowcran.paper_fetch.downloader import SourceBase

logger = logging.getLogger(__name__)


class PMCSource(SourceBase):
    name = "PMC"
    priority = 40
    timeout = 30

    # NCBI ID Converter API: PMID/DOI -> PMCID
    _ID_CONV_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids={ids}&format=json"
    # EuropePMC PDF render (most reliable for PMC PDFs)
    _EUROPEPMC_PDF_URL = "https://europepmc.org/articles/{pmcid}?pdf=render"

    def fetch(self, doi: str | None, arxiv_id: str | None,
              title: str | None = None, pmid: str | None = None) -> tuple[bytes | None, str | None]:
        # Need at least one identifier to look up PMCID
        if not doi and not pmid:
            return None, "No DOI or PMID"

        # Step 1: Find PMCID via NCBI ID Converter
        pmcid = self._lookup_pmcid(doi, pmid)
        if not pmcid:
            return None, "No PMCID found"

        # Step 2: Try EuropePMC PDF render (most reliable)
        try:
            pdf_url = self._EUROPEPMC_PDF_URL.format(pmcid=pmcid)
            resp = requests.get(pdf_url, timeout=self.timeout,
                                allow_redirects=True,
                                headers={"User-Agent": "KnowCran/1.1"})
            if resp.status_code == 200 and len(resp.content) > 1024:
                ct = resp.headers.get("content-type", "")
                if "pdf" in ct or resp.content[:4] == b"%PDF":
                    return resp.content, None
        except requests.RequestException:
            pass

        return None, f"PMC PDF download failed for {pmcid}"

    def _lookup_pmcid(self, doi: str | None, pmid: str | None) -> str | None:
        """Convert PMID or DOI to PMCID using NCBI ID Converter API."""
        # Prefer PMID (direct mapping), fallback to DOI
        lookup_id = pmid or doi
        if not lookup_id:
            return None

        try:
            url = self._ID_CONV_URL.format(ids=lookup_id)
            resp = requests.get(url, timeout=self.timeout,
                                headers={"User-Agent": "KnowCran/1.1"})
            if resp.status_code != 200:
                logger.debug(f"ID Converter returned {resp.status_code}")
                return None

            data = resp.json()
            records = data.get("records", [])
            for record in records:
                pmcid = record.get("pmcid")
                if pmcid:
                    return pmcid

            return None
        except (requests.RequestException, ValueError) as e:
            logger.debug(f"ID Converter lookup failed: {e}")
            return None
