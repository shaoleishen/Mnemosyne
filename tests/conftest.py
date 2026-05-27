"""Shared test fixtures."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from knowcran.models import PaperRecord


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES_DIR / name).read_text())


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data" / "raw" / "semantic_scholar"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.sqlite"


@pytest.fixture
def sample_paper() -> dict[str, Any]:
    return load_fixture("s2_search_response.json")["data"][0]


@pytest.fixture
def sample_papers() -> list[dict[str, Any]]:
    return load_fixture("s2_search_response.json")["data"]


@pytest.fixture
def sample_paper_record(sample_paper: dict[str, Any]) -> PaperRecord:
    return PaperRecord.from_s2(sample_paper)


@pytest.fixture
def mock_s2_client() -> MagicMock:
    client = MagicMock()
    client.search_bulk.return_value = load_fixture("s2_search_response.json")["data"]
    client.get_paper.return_value = load_fixture("s2_paper_detail.json")
    client.get_recommendations.return_value = load_fixture("s2_recommendations.json")["recommendedPapers"]
    client.get_recommendations_for_paper.return_value = load_fixture("s2_recommendations.json")["recommendedPapers"]
    client.close.return_value = None
    return client
