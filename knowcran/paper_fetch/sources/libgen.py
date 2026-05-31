"""LibGen source - grey literature repository.

WARNING: This source may not comply with publisher terms of service.
See docs/fulltext-migration-notes.md for compliance considerations.
"""

from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from knowcran.paper_fetch.downloader import SourceBase

logger = logging.getLogger(__name__)


class LibGenSource(SourceBase):
    name = "LibGen"
    priority = 80
    is_grey = True
    timeout = 30

    _SEARCH_URL = "https://libgen.is/scimag/?q={doi}"

    def fetch(self, doi: str | None, arxiv_id: str | None,
              title: str | None = None) -> tuple[bytes | None, str | None]:
        if not doi:
            return None, "No DOI"
        try:
            # Search by DOI
            search_url = self._SEARCH_URL.format(doi=doi)
            resp = requests.get(search_url, timeout=self.timeout,
                                headers={"User-Agent": "KnowCran/1.1"})
            if resp.status_code != 200:
                return None, f"Search returned {resp.status_code}"

            # Parse search results for download link
            soup = BeautifulSoup(resp.text, "html.parser")
            # Look for download links
            links = soup.find_all("a", href=True)
            for link in links:
                href = link.get("href", "")
                if "/get.php" in href or "/download.php" in href:
                    # Follow download link
                    if not href.startswith("http"):
                        href = f"https://libgen.is{href}"
                    pdf_resp = requests.get(href, timeout=self.timeout,
                                            allow_redirects=True,
                                            headers={"User-Agent": "KnowCran/1.1"})
                    if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1024:
                        return pdf_resp.content, None
            return None, "Not found on LibGen"
        except requests.RequestException as e:
            return None, str(e)
        except Exception as e:
            return None, f"Parse error: {e}"
