"""Semantic Scholar client contract tests with MockTransport."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from knowcran.config import DEFAULT_FIELDS, S2_BASE_URL
from knowcran.semantic_scholar import SemanticScholarClient
from knowcran.utils import cache_key


def _mock_handler(request: httpx.Request) -> httpx.Response:
    """Route requests to mock responses based on URL path and method."""
    path = request.url.path
    method = request.method

    if path == "/graph/v1/paper/search/bulk" and method == "GET":
        # Verify required params
        params = dict(request.url.params)
        assert "query" in params, "search_bulk must send query param"
        assert "fields" in params, "search_bulk must send fields param"
        token = params.get("token")
        if token:
            return httpx.Response(200, json={
                "data": [{"paperId": "p2", "title": "Page 2"}],
                "token": None,
            })
        return httpx.Response(200, json={
            "data": [{"paperId": "p1", "title": "Test Paper"}],
            "token": "page2",
        })

    if path == "/graph/v1/paper/p1" and method == "GET":
        params = dict(request.url.params)
        assert "fields" in params, "get_paper must send fields param"
        return httpx.Response(200, json={
            "paperId": "p1",
            "title": "Test Paper",
        })

    if path == "/graph/v1/paper/batch" and method == "POST":
        params = dict(request.url.params)
        assert "fields" in params, "batch_papers must send fields as query param"
        body = json.loads(request.content)
        assert "ids" in body, "batch_papers must send ids in body"
        ids = body["ids"]
        return httpx.Response(200, json=[
            {"paperId": pid, "title": f"Paper {pid}"} for pid in ids
        ])

    if path == "/recommendations/v1/papers" and method == "POST":
        params = dict(request.url.params)
        assert "limit" in params, "get_recommendations must send limit param"
        assert "fields" in params, "get_recommendations must send fields param"
        body = json.loads(request.content)
        assert "positivePaperIds" in body, "get_recommendations must send positivePaperIds"
        assert "negativePaperIds" in body, "get_recommendations must send negativePaperIds"
        return httpx.Response(200, json={
            "recommendedPapers": [{"paperId": "rec1", "title": "Recommended"}],
        })

    if path == "/recommendations/v1/papers/forpaper/p1" and method == "GET":
        params = dict(request.url.params)
        assert "limit" in params
        assert "fields" in params
        return httpx.Response(200, json={
            "recommendedPapers": [{"paperId": "rec2", "title": "Rec For Paper"}],
        })

    return httpx.Response(404, json={"error": "not found"})


def _make_client(tmp_path: Path) -> SemanticScholarClient:
    transport = httpx.MockTransport(_mock_handler)
    http_client = httpx.Client(transport=transport, timeout=5.0)
    return SemanticScholarClient(api_key="test-key", rate_limit=0.0, raw_dir=tmp_path / "cache", client=http_client)


@pytest.fixture
def mock_client(tmp_path: Path) -> SemanticScholarClient:
    return _make_client(tmp_path)


def test_search_bulk_sends_correct_params(mock_client: SemanticScholarClient) -> None:
    results = mock_client.search_bulk("celiac", limit=1)
    assert len(results) == 1
    assert results[0]["paperId"] == "p1"


def test_search_bulk_follows_pagination(mock_client: SemanticScholarClient) -> None:
    results = mock_client.search_bulk("celiac", limit=100)
    assert len(results) == 2
    assert results[0]["paperId"] == "p1"
    assert results[1]["paperId"] == "p2"


def test_search_bulk_respects_limit(mock_client: SemanticScholarClient) -> None:
    results = mock_client.search_bulk("celiac", limit=1)
    assert len(results) == 1


def test_get_paper_sends_correct_params(mock_client: SemanticScholarClient) -> None:
    result = mock_client.get_paper("p1")
    assert result["paperId"] == "p1"


def test_batch_papers_sends_post_with_ids_and_fields(mock_client: SemanticScholarClient) -> None:
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

    params = json.dumps({"query": "test", "fields": DEFAULT_FIELDS}, sort_keys=True)
    key = cache_key("GET", f"{S2_BASE_URL}/graph/v1/paper/search/bulk", params)
    cached_data = {"data": [{"paperId": "cached", "title": "Cached Paper"}], "token": None}
    (cache_dir / f"{key}.json").write_text(json.dumps(cached_data))

    client = SemanticScholarClient(api_key="", rate_limit=0.0, raw_dir=cache_dir)
    results = client.search_bulk("test")
    assert results[0]["paperId"] == "cached"
    client.close()


def test_recommendations_cached_on_second_call(tmp_path: Path) -> None:
    """Second call to get_recommendations should be served from cache."""
    client = _make_client(tmp_path)
    first = client.get_recommendations(["p1"])
    assert first[0]["paperId"] == "rec1"

    # Second call should come from cache (no network)
    second = client.get_recommendations(["p1"])
    assert second[0]["paperId"] == "rec1"
    client.close()


def test_retry_on_429(tmp_path: Path) -> None:
    """Client retries on 429 and eventually succeeds."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] < 3:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json={"paperId": "p1", "title": "OK"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, timeout=5.0)
    client = SemanticScholarClient(api_key="", rate_limit=0.0, raw_dir=tmp_path / "cache", client=http_client)
    result = client.get_paper("p1")
    assert result["paperId"] == "p1"
    assert call_count["n"] == 3
    client.close()


def test_retry_on_500(tmp_path: Path) -> None:
    """Client retries on 500."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] < 2:
            return httpx.Response(500, json={"error": "server error"})
        return httpx.Response(200, json={"paperId": "p1", "title": "OK"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, timeout=5.0)
    client = SemanticScholarClient(api_key="", rate_limit=0.0, raw_dir=tmp_path / "cache", client=http_client)
    result = client.get_paper("p1")
    assert result["paperId"] == "p1"
    assert call_count["n"] == 2
    client.close()


def test_does_not_close_injected_client(tmp_path: Path) -> None:
    """Client injected externally should not be closed by SemanticScholarClient."""
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    http_client = httpx.Client(transport=transport, timeout=5.0)
    client = SemanticScholarClient(api_key="", rate_limit=0.0, raw_dir=tmp_path / "cache", client=http_client)
    client.close()
    # Should not raise - the injected client is still usable
    http_client.get("https://example.com")
