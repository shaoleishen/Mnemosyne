"""Configuration management for KnowCran."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

S2_BASE_URL = "https://api.semanticscholar.org"

DEFAULT_FIELDS = ",".join([
    "paperId", "title", "abstract", "year", "publicationDate", "venue",
    "authors", "externalIds", "citationCount", "referenceCount",
    "influentialCitationCount", "fieldsOfStudy", "s2FieldsOfStudy",
    "openAccessPdf", "url",
])

EXPANDED_FIELDS = DEFAULT_FIELDS + ",references,citations"

DISCOVERY_QUERIES = [
    "{q}",
    "{q} mechanism",
    "{q} treatment",
    "{q} review",
    "{q} clinical",
]


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("KNOWCRAN_DATA_DIR", "data")))
    vault_dir: Path = field(default_factory=lambda: Path(os.getenv("KNOWCRAN_VAULT_DIR", "vault")))
    rate_limit_seconds: float = field(default_factory=lambda: float(os.getenv("KNOWCRAN_RATE_LIMIT_SECONDS", "1.1")))
    s2_api_key: str = field(default_factory=lambda: os.getenv("SEMANTIC_SCHOLAR_API_KEY", ""))

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw" / "semantic_scholar"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "knowcran.sqlite"

    @classmethod
    def from_env(cls) -> Settings:
        return cls()


# Module-level defaults for backward compatibility
_default = Settings()
DATA_DIR = _default.data_dir
VAULT_DIR = _default.vault_dir
RAW_DIR = _default.raw_dir
DB_PATH = _default.db_path
RATE_LIMIT_SECONDS = _default.rate_limit_seconds
S2_API_KEY = _default.s2_api_key
