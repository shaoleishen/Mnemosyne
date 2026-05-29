"""Configuration management for KnowCran."""

from __future__ import annotations

import os
import shutil
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


def _detect_claw_bin() -> str | None:
    """Detect Claw binary path following the priority order from the goal plan."""
    env = os.getenv("MNEMOSYNE_CLAW_BIN")
    if env and Path(env).exists():
        return env
    # Sibling paths
    for rel in [
        "../claw-code-main/rust/target/debug/claw.exe",
        "../claw-code-main/rust/target/debug/claw",
    ]:
        p = Path(rel)
        if p.exists():
            return str(p.resolve())
    # On PATH
    found = shutil.which("claw")
    return found


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("KNOWCRAN_DATA_DIR", "data")))
    vault_dir: Path = field(default_factory=lambda: Path(os.getenv("KNOWCRAN_VAULT_DIR", "vault")))
    rate_limit_seconds: float = field(default_factory=lambda: float(os.getenv("KNOWCRAN_RATE_LIMIT_SECONDS", "1.1")))
    s2_api_key: str = field(default_factory=lambda: os.getenv("SEMANTIC_SCHOLAR_API_KEY", ""))

    # LLM provider settings
    llm_provider: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_LLM_PROVIDER", "none"))
    claw_bin: str | None = field(default_factory=_detect_claw_bin)
    claw_model: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_CLAW_MODEL", "sonnet"))
    claw_permission_mode: str = field(default_factory=lambda: os.getenv("MNEMOSYNE_CLAW_PERMISSION_MODE", "read-only"))
    claw_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("MNEMOSYNE_CLAW_TIMEOUT_SECONDS", "600")))
    claw_max_retries: int = field(default_factory=lambda: int(os.getenv("MNEMOSYNE_CLAW_MAX_RETRIES", "2")))
    llm_cache_dir: Path = field(default_factory=lambda: Path(os.getenv("MNEMOSYNE_LLM_CACHE_DIR", "data/raw/llm")))

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
