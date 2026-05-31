"""Configuration for PDF download sources and strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Strategy(str, Enum):
    """Download strategy determines which sources are tried and in what order."""
    FASTEST = "fastest"        # All sources race in parallel
    OA_FIRST = "oa_first"      # Open access first, grey sources fallback
    LEGAL_ONLY = "legal_only"  # Only legal/open access sources
    SCIHUB_ONLY = "scihub_only"  # Sci-Hub only


@dataclass
class SourceConfig:
    """Configuration for a single download source."""
    name: str
    enabled: bool = True
    priority: int = 50  # Lower = higher priority
    timeout_seconds: int = 30
    base_url: str = ""
    # Whether this is a "grey" source (Sci-Hub, LibGen)
    is_grey: bool = False


@dataclass
class DownloadConfig:
    """Overall download configuration."""
    strategy: Strategy = Strategy.FASTEST
    pdf_dir: str = "data/pdfs"
    max_workers: int = 5
    timeout_seconds: int = 60
    sources: list[SourceConfig] = field(default_factory=list)

    def get_enabled_sources(self) -> list[SourceConfig]:
        """Get sources enabled for the current strategy."""
        enabled = []
        for src in self.sources:
            if not src.enabled:
                continue
            if self.strategy == Strategy.LEGAL_ONLY and src.is_grey:
                continue
            if self.strategy == Strategy.SCIHUB_ONLY and src.name != "Sci-Hub":
                continue
            enabled.append(src)
        return sorted(enabled, key=lambda s: s.priority)


# Default source configurations
DEFAULT_SOURCES = [
    SourceConfig(name="arXiv", priority=10, base_url="https://arxiv.org"),
    SourceConfig(name="Unpaywall", priority=20, base_url="https://api.unpaywall.org"),
    SourceConfig(name="OpenAlex", priority=25, base_url="https://api.openalex.org"),
    SourceConfig(name="SemanticScholar", priority=30, base_url="https://api.semanticscholar.org"),
    SourceConfig(name="EuropePMC", priority=35, base_url="https://europepmc.org"),
    SourceConfig(name="PMC", priority=40, base_url="https://www.ncbi.nlm.nih.gov/pmc"),
    SourceConfig(name="CORE", priority=45, base_url="https://api.core.ac.uk"),
    SourceConfig(name="DOAJ", priority=50, base_url="https://doaj.org"),
    SourceConfig(name="Crossref", priority=55, base_url="https://api.crossref.org"),
    SourceConfig(name="Publishers", priority=60, base_url=""),
    SourceConfig(name="LibGen", priority=80, is_grey=True, base_url="https://libgen.is"),
    SourceConfig(name="Sci-Hub", priority=90, is_grey=True, base_url="https://sci-hub.se"),
]


def default_download_config(
    strategy: str = "fastest",
    pdf_dir: str = "data/pdfs",
    scihub_enabled: bool = True,
    libgen_enabled: bool = True,
    max_workers: int = 5,
) -> DownloadConfig:
    """Create a download config with default sources."""
    sources = []
    for src in DEFAULT_SOURCES:
        cfg = SourceConfig(
            name=src.name,
            enabled=src.enabled,
            priority=src.priority,
            base_url=src.base_url,
            is_grey=src.is_grey,
            timeout_seconds=src.timeout_seconds,
        )
        # Disable grey sources if configured
        if src.name == "Sci-Hub" and not scihub_enabled:
            cfg.enabled = False
        if src.name == "LibGen" and not libgen_enabled:
            cfg.enabled = False
        sources.append(cfg)

    return DownloadConfig(
        strategy=Strategy(strategy),
        pdf_dir=pdf_dir,
        max_workers=max_workers,
        sources=sources,
    )
