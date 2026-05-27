"""Utility functions for KnowCran."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from math import log1p
from typing import Any


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


def relevance_score(title: str, abstract: str, query: str, citation_count: int, year: int | None, has_oa: bool, current_year: int | None = None) -> float:
    query_terms = set(query.lower().split())
    title_lower = title.lower()
    abstract_lower = (abstract or "").lower()

    title_overlap = sum(1 for t in query_terms if t in title_lower) / max(len(query_terms), 1)
    abstract_overlap = sum(1 for t in query_terms if t in abstract_lower) / max(len(query_terms), 1)

    citation_score = log1p(citation_count or 0) / 10.0

    current_year = current_year or datetime.now().year
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


def paper_note_stem(paper: dict[str, Any]) -> str:
    return f"{paper.get('year', 'unknown')}_{slugify(paper['title'])}"


def citation_key(paper: dict[str, Any]) -> str:
    authors_str = ""
    try:
        authors_list = json.loads(paper.get("authors_json") or "[]")
        if authors_list:
            first_author = authors_list[0].get("name", "")
            # Extract last name (last word before comma or last word)
            parts = first_author.replace(",", " ").split()
            authors_str = slugify(parts[-1]) if parts else ""
    except Exception:
        pass

    year = paper.get("year") or "nd"
    title_words = slugify(paper.get("title", "")).split("-")
    short_title = title_words[0] if title_words else "untitled"

    if authors_str:
        return f"{authors_str}{year}{short_title}"
    return f"{year}{short_title}"
