"""PDF download sources."""

from knowcran.paper_fetch.sources.arxiv import ArxivSource
from knowcran.paper_fetch.sources.unpaywall import UnpaywallSource
from knowcran.paper_fetch.sources.openalex import OpenAlexSource
from knowcran.paper_fetch.sources.semantic_scholar import SemanticScholarSource
from knowcran.paper_fetch.sources.europepmc import EuropePMCSource
from knowcran.paper_fetch.sources.pmc import PMCSource
from knowcran.paper_fetch.sources.core import CORESource
from knowcran.paper_fetch.sources.doaj import DOAJSource
from knowcran.paper_fetch.sources.crossref import CrossrefSource
from knowcran.paper_fetch.sources.publishers import PublishersSource
from knowcran.paper_fetch.sources.libgen import LibGenSource
from knowcran.paper_fetch.sources.scihub import SciHubSource

__all__ = [
    "ArxivSource",
    "UnpaywallSource",
    "OpenAlexSource",
    "SemanticScholarSource",
    "EuropePMCSource",
    "PMCSource",
    "CORESource",
    "DOAJSource",
    "CrossrefSource",
    "PublishersSource",
    "LibGenSource",
    "SciHubSource",
]
