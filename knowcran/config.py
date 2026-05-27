"""Configuration management for KnowCran."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("KNOWCRAN_DATA_DIR", "data"))
VAULT_DIR = Path(os.getenv("KNOWCRAN_VAULT_DIR", "vault"))
RAW_DIR = DATA_DIR / "raw" / "semantic_scholar"
DB_PATH = DATA_DIR / "knowcran.sqlite"
RATE_LIMIT_SECONDS = float(os.getenv("KNOWCRAN_RATE_LIMIT_SECONDS", "1.1"))
S2_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")

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
