"""Semantic Scholar client contract tests with MockTransport."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from knowcran.config import S2_BASE_URL
from knowcran.semantic_scholar import SemanticScholarClient


def _mock_handler(request: httpx.Request) -> httpx.Response:
    """Route requests to mock responses based on URL path."""
    path = request.url.path

    if path == "/graph/v1/paper/search/bulk":
        return httpx.Response(200, json={
            "data": [{"paperId": "p1", "title": "Test Paper"}],
            "token": None,
        })

    if path == "/graph/v1/paper/p1":
        return httpx.Response(200, json={
            "paperId": "p1",
            "title": "Test Paper",
            "references": [{"paperId": "ref1", "title": "Ref Paper"}],
        })

    if path == "/graph/v1/paper/batch":
        body = json.loads(request.content)
        ids = body.get("ids", [])
        return httpx.Response(200, json=[
            {"paperId": pid, "title": f"Paper {pid}"} for pid in ids
        ])

    if path == "/recommendations/v1/papers":
        return httpx.Response(200, json={
            "recommendedPapers": [{"paperId": "rec1", "title": "Recommended"}],
        })

    if path == "/recommendations/v1/papers/forpaper/p1":
        return httpx.Response(200, json={
            "recommendedPapers": [{"paperId": "rec2", "title": "Rec For Paper"}],
        })

    return httpx.Response(404, json={"error": "not found"})


@pytest.fixture
def mock_client(tmp_path: Path) -> SemanticScholarClient:
    client = SemanticScholarClient(api_key="test-key", rate_limit=0.0, raw_dir=tmp_path / "cache")
    client._client = httpx.Client(transport=httpx.MockTransport(_mock_handler), timeout=5.0)
    return client


def test_search_bulk_sends_correct_params(mock_client: SemanticScholarClient) -> None:
    results = mock_client.search_bulk("celiac", limit=10)
    assert len(results) == 1
    assert results[0]["paperId"] == "p1"


def test_batch_papers_sends_post_with_ids(mock_client: SemanticScholarClient) -> None:
    results = mock_client.batch_papers(["p1", "p2"])
    assert len(results) == 2
    assert results[0]["paperId"] == "p1"
    assert results[1]["paperId"] == "p2"


def test_get_recommendations_multi_seed(mock_client: SemanticScholarClient) -> None:
    results = mock_client.get_recommendations(["p1", "p2"])
    assert len(results) == 1
    assert results[0]["paperId"] == "rec1"


def test_get_recommendations_for_paper(mock_client: SemanticScholarClient) -> None:
    results = mock_client.get_recommendations_for_paper("p1")
    assert len(results) == 1
    assert results[0]["paperId"] == "rec2"


def test_cache_hit_skips_network(tmp_path: Path) -> None:
    """Pre-populate cache and verify no network call needed."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    from knowcran.config import DEFAULT_FIELDS
    from knowcran.utils import cache_key
    params = json.dumps({"query": "test", "fields": DEFAULT_FIELDS}, sort_keys=True)
    key = cache_key("GET", f"{S2_BASE_URL}/graph/v1/paper/search/bulk", params)
    cached_data = {"data": [{"paperId": "cached", "title": "Cached Paper"}], "token": None}
    (cache_dir / f"{key}.json").write_text(json.dumps(cached_data))

    client = SemanticScholarClient(api_key="", rate_limit=0.0, raw_dir=cache_dir)
    # Should return cached data without making any HTTP call
    results = client.search_bulk("test")
    assert results[0]["paperId"] == "cached"
    client.close()


def test_retry_on_429(tmp_path: Path) -> None:
    """Client retries on 429 and eventually succeeds."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] < 3:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json={"paperId": "p1", "title": "OK"})

    client = SemanticScholarClient(api_key="", rate_limit=0.0, raw_dir=tmp_path / "cache")
    client._client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)
    result = client.get_paper("p1")
    assert result["paperId"] == "p1"
    assert call_count["n"] == 3
    client.close()
