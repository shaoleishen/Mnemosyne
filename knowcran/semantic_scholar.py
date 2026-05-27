"""Semantic Scholar API client with rate limiting, retries, and caching."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from knowcran.config import RATE_LIMIT_SECONDS, RAW_DIR, S2_API_KEY, S2_BASE_URL, DEFAULT_FIELDS, EXPANDED_FIELDS
from knowcran.utils import cache_key

_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3


class SemanticScholarClient:
    def __init__(self, api_key: str = S2_API_KEY, rate_limit: float = RATE_LIMIT_SECONDS, raw_dir: Path = RAW_DIR):
        self._api_key = api_key
        self._rate_limit = rate_limit
        self._last_request_time = 0.0
        self._raw_dir = raw_dir
        self._raw_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(timeout=30.0)

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json"}
        if self._api_key:
            h["x-api-key"] = self._api_key
        return h

    def _wait_rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit:
            time.sleep(self._rate_limit - elapsed)
        self._last_request_time = time.time()

    def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        key = cache_key("GET", url, json.dumps(params or {}, sort_keys=True))
        cache_file = self._raw_dir / f"{key}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text())

        for attempt in range(_MAX_RETRIES):
            self._wait_rate_limit()
            resp = self._client.get(url, headers=self._headers(), params=params)
            if resp.status_code == 200:
                data = resp.json()
                cache_file.write_text(json.dumps(data, indent=2))
                return data
            if resp.status_code in _RETRY_STATUS:
                wait = (attempt + 1) * 2
                time.sleep(wait)
                continue
            resp.raise_for_status()
        resp.raise_for_status()  # type: ignore[union-attr]
        return {}

    def _post(self, url: str, body: dict[str, Any], params: dict[str, Any] | None = None) -> Any:
        body_str = json.dumps(body, sort_keys=True)
        cache_input = body_str + json.dumps(params or {}, sort_keys=True)
        key = cache_key("POST", url, cache_input)
        cache_file = self._raw_dir / f"{key}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text())

        for attempt in range(_MAX_RETRIES):
            self._wait_rate_limit()
            resp = self._client.post(url, headers=self._headers(), json=body, params=params)
            if resp.status_code == 200:
                data = resp.json()
                cache_file.write_text(json.dumps(data, indent=2))
                return data
            if resp.status_code in _RETRY_STATUS:
                wait = (attempt + 1) * 2
                time.sleep(wait)
                continue
            resp.raise_for_status()
        resp.raise_for_status()  # type: ignore[union-attr]
        return {}

    def search_bulk(self, query: str, limit: int = 100, fields: str = DEFAULT_FIELDS) -> list[dict[str, Any]]:
        url = f"{S2_BASE_URL}/graph/v1/paper/search/bulk"
        params: dict[str, Any] = {"query": query, "fields": fields}
        data = self._get(url, params)
        papers = data.get("data", [])
        token = data.get("token")
        while token and len(papers) < limit:
            params["token"] = token
            data = self._get(url, params)
            batch = data.get("data", [])
            if not batch:
                break
            papers.extend(batch)
            token = data.get("token")
        return papers[:limit]

    def get_paper(self, paper_id: str, fields: str = DEFAULT_FIELDS) -> dict[str, Any]:
        url = f"{S2_BASE_URL}/graph/v1/paper/{paper_id}"
        return self._get(url, {"fields": fields})

    def batch_papers(self, paper_ids: list[str], fields: str = DEFAULT_FIELDS) -> list[dict[str, Any]]:
        url = f"{S2_BASE_URL}/graph/v1/paper/batch"
        params = {"fields": fields}
        body = {"ids": paper_ids}
        data = self._post(url, body=body, params=params)
        return data if isinstance(data, list) else []

    def get_recommendations(
        self,
        seed_paper_ids: list[str],
        positive_paper_ids: list[str] | None = None,
        negative_paper_ids: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        url = f"{S2_BASE_URL}/recommendations/v1/papers"
        body: dict[str, Any] = {
            "positivePaperIds": seed_paper_ids + (positive_paper_ids or []),
            "negativePaperIds": negative_paper_ids or [],
        }
        params = {"limit": limit, "fields": DEFAULT_FIELDS}
        for attempt in range(_MAX_RETRIES):
            self._wait_rate_limit()
            resp = self._client.post(url, headers=self._headers(), json=body, params=params)
            if resp.status_code == 200:
                return resp.json().get("recommendedPapers", [])
            if resp.status_code in _RETRY_STATUS:
                time.sleep((attempt + 1) * 2)
                continue
            resp.raise_for_status()
        return []

    def get_recommendations_for_paper(self, paper_id: str, limit: int = 20) -> list[dict[str, Any]]:
        url = f"{S2_BASE_URL}/recommendations/v1/papers/forpaper/{paper_id}"
        params = {"limit": limit, "fields": DEFAULT_FIELDS}
        return self._get(url, params).get("recommendedPapers", [])

    def close(self) -> None:
        self._client.close()
