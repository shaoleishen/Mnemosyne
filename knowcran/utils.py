"""Utility functions for KnowCran."""

from __future__ import annotations

import hashlib
import re
from math import log1p


def slugify(text: str, max_len: int = 80) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:max_len]


def normalize_title(title: str) -> str:
    t = title.lower().strip()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def cache_key(method: str, url: str, body: str = "") -> str:
    raw = f"{method}:{url}:{body}"
    return hashlib.sha256(raw.encode()).hexdigest()


def relevance_score(title: str, abstract: str, query: str, citation_count: int, year: int | None, has_oa: bool) -> float:
    query_terms = set(query.lower().split())
    title_lower = title.lower()
    abstract_lower = (abstract or "").lower()

    title_overlap = sum(1 for t in query_terms if t in title_lower) / max(len(query_terms), 1)
    abstract_overlap = sum(1 for t in query_terms if t in abstract_lower) / max(len(query_terms), 1)

    citation_score = log1p(citation_count or 0) / 10.0

    current_year = 2026
    recency = max(0, min(1, ((year or 2020) - 2000) / (current_year - 2000)))

    oa_bonus = 0.1 if has_oa else 0.0

    score = (
        title_overlap * 0.35
        + abstract_overlap * 0.25
        + citation_score * 0.2
        + recency * 0.15
        + oa_bonus * 0.05
    )
    return round(score, 4)


def generate_queries(question: str) -> list[str]:
    return [
        question,
        f"{question} mechanism",
        f"{question} treatment",
        f"{question} review",
        f"{question} clinical",
    ]
