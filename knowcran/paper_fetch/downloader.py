"""PDF download orchestrator with multi-source racing."""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from knowcran.paper_fetch.cache import PDFCache
from knowcran.paper_fetch.config import DownloadConfig, Strategy, default_download_config
from knowcran.paper_fetch.identifiers import normalize_doi, detect_arxiv_id
from knowcran.paper_fetch.pdf_utils import validate_pdf, safe_filename, compute_sha256

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    """Result of a PDF download attempt."""
    success: bool
    identifier: str  # DOI or arXiv ID
    doi: str | None = None
    arxiv_id: str | None = None
    source: str | None = None
    file_path: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    error: str | None = None
    asset_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "identifier": self.identifier,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "source": self.source,
            "file": self.file_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "error": self.error,
            "asset_id": self.asset_id,
        }


class SourceBase:
    """Base class for PDF download sources."""

    name: str = "unknown"
    priority: int = 50
    is_grey: bool = False
    timeout: int = 30

    def fetch(self, doi: str | None, arxiv_id: str | None,
              title: str | None = None) -> tuple[bytes | None, str | None]:
        """Attempt to download a PDF.

        Returns (pdf_bytes, error_message). If successful, error is None.
        If failed, pdf_bytes is None and error describes the failure.
        """
        raise NotImplementedError


def _get_all_sources() -> list[type[SourceBase]]:
    """Get all available source classes."""
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

    return [
        ArxivSource,
        UnpaywallSource,
        OpenAlexSource,
        SemanticScholarSource,
        EuropePMCSource,
        PMCSource,
        CORESource,
        DOAJSource,
        CrossrefSource,
        PublishersSource,
        LibGenSource,
        SciHubSource,
    ]


def _try_source(source_cls: type[SourceBase], doi: str | None,
                arxiv_id: str | None, title: str | None) -> DownloadResult | None:
    """Try a single source and return a result or None."""
    source = source_cls()
    try:
        data, error = source.fetch(doi=doi, arxiv_id=arxiv_id, title=title)
        if data is None:
            return None
        valid, val_err = validate_pdf(data)
        if not valid:
            logger.debug(f"{source.name}: invalid PDF - {val_err}")
            return None
        return DownloadResult(
            success=True,
            identifier=doi or arxiv_id or "unknown",
            doi=doi,
            arxiv_id=arxiv_id,
            source=source.name,
            sha256=compute_sha256(data),
            size_bytes=len(data),
            _data=data,
        )
    except Exception as e:
        logger.debug(f"{source.name} failed: {e}")
        return None


def download_pdf(
    doi: str | None = None,
    arxiv_id: str | None = None,
    title: str | None = None,
    paper_id: str | None = None,
    strategy: str = "fastest",
    pdf_dir: str = "data/pdfs",
    scihub_enabled: bool = True,
    libgen_enabled: bool = True,
    force: bool = False,
) -> DownloadResult:
    """Download a PDF from available sources.

    Resolution order: DOI -> arXiv ID -> title search.
    Strategy determines which sources are tried and how.
    """
    # Normalize identifiers
    doi = normalize_doi(doi) if doi else None
    arxiv_id = detect_arxiv_id(arxiv_id) if arxiv_id else None
    identifier = doi or arxiv_id or title or "unknown"

    if not doi and not arxiv_id and not title:
        return DownloadResult(
            success=False,
            identifier=identifier,
            error="No DOI, arXiv ID, or title provided",
        )

    # Check cache unless forced
    cache = PDFCache(pdf_dir)
    if not force:
        if doi:
            cached = cache.find_by_doi(doi)
            if cached:
                return DownloadResult(
                    success=True,
                    identifier=identifier,
                    doi=doi,
                    source="cache",
                    file_path=str(cached),
                    sha256=cache.get_sha256(cached),
                    size_bytes=cached.stat().st_size,
                )
        if arxiv_id:
            cached = cache.find_by_arxiv_id(arxiv_id)
            if cached:
                return DownloadResult(
                    success=True,
                    identifier=identifier,
                    arxiv_id=arxiv_id,
                    source="cache",
                    file_path=str(cached),
                    sha256=cache.get_sha256(cached),
                    size_bytes=cached.stat().st_size,
                )

    # Get source configs
    config = default_download_config(
        strategy=strategy,
        pdf_dir=pdf_dir,
        scihub_enabled=scihub_enabled,
        libgen_enabled=libgen_enabled,
    )

    # Build source class list matching enabled config
    all_sources = _get_all_sources()
    source_name_map = {s.__name__.replace("Source", ""): s for s in all_sources}
    enabled_sources = []
    for src_cfg in config.get_enabled_sources():
        for src_cls in all_sources:
            if src_cls.name == src_cfg.name:
                enabled_sources.append(src_cls)
                break

    if not enabled_sources:
        return DownloadResult(
            success=False,
            identifier=identifier,
            error="No sources enabled for strategy",
        )

    # Race sources
    if config.strategy == Strategy.FASTEST:
        return _race_sources(enabled_sources, doi, arxiv_id, title, identifier, cache, pdf_dir)
    else:
        return _sequential_sources(enabled_sources, doi, arxiv_id, title, identifier, cache, pdf_dir)


def _race_sources(sources: list[type[SourceBase]], doi: str | None,
                   arxiv_id: str | None, title: str | None, identifier: str,
                   cache: PDFCache, pdf_dir: str) -> DownloadResult:
    """Race all sources in parallel, return the first success."""
    with ThreadPoolExecutor(max_workers=min(len(sources), 5)) as executor:
        futures = {
            executor.submit(_try_source, src, doi, arxiv_id, title): src
            for src in sources
        }
        for future in as_completed(futures, timeout=60):
            try:
                result = future.result()
                if result and result.success:
                    # Store in cache
                    filename = safe_filename(title or "", doi)
                    result.file_path = str(cache.store(result._data, filename))
                    del result._data
                    return result
            except Exception as e:
                logger.debug(f"Source {futures[future].name} exception: {e}")

    return DownloadResult(
        success=False,
        identifier=identifier,
        error="All sources failed",
    )


def _sequential_sources(sources: list[type[SourceBase]], doi: str | None,
                         arxiv_id: str | None, title: str | None, identifier: str,
                         cache: PDFCache, pdf_dir: str) -> DownloadResult:
    """Try sources sequentially in priority order."""
    for src_cls in sources:
        result = _try_source(src_cls, doi, arxiv_id, title)
        if result and result.success:
            filename = safe_filename(title or "", doi)
            result.file_path = str(cache.store(result._data, filename))
            del result._data
            return result

    return DownloadResult(
        success=False,
        identifier=identifier,
        error="All sources failed",
    )
