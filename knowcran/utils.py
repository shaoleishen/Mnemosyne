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


def relevance_score(
    title: str,
    abstract: str,
    query: str,
    citation_count: int,
    year: int | None,
    has_oa: bool,
    current_year: int | None = None,
    fields_of_study: list[str] | None = None,
) -> float:
    query_lower = query.lower().strip()
    query_terms = set(query_lower.split())
    title_lower = title.lower()
    abstract_lower = (abstract or "").lower()

    # Exact phrase match boost
    exact_title_boost = 1.0 if query_lower in title_lower else 0.0
    exact_abstract_boost = 0.5 if query_lower in abstract_lower else 0.0

    # Term overlap (tokenized)
    title_overlap = sum(1 for t in query_terms if t in title_lower) / max(len(query_terms), 1)
    abstract_overlap = sum(1 for t in query_terms if t in abstract_lower) / max(len(query_terms), 1)

    # Title phrase boost: reward papers where most query terms appear in title
    title_phrase_score = min(1.0, title_overlap * 1.5)

    # No abstract penalty
    no_abstract_penalty = 0.3 if not abstract or abstract.strip() == "" else 0.0

    # Biomedical field preference
    bio_bonus = 0.0
    if fields_of_study:
        bio_terms = {"medicine", "biology", "biochemistry", "genetics", "neuroscience", "psychology", "health sciences"}
        if any(f.lower() in bio_terms for f in fields_of_study):
            bio_bonus = 0.15

    # Citation and recency
    citation_score = log1p(citation_count or 0) / 10.0
    current_year = current_year or datetime.now().year
    recency = max(0, min(1, ((year or 2020) - 2000) / (current_year - 2000)))
    oa_bonus = 0.1 if has_oa else 0.0

    score = (
        exact_title_boost * 0.25
        + exact_abstract_boost * 0.1
        + title_phrase_score * 0.2
        + abstract_overlap * 0.15
        + bio_bonus * 0.1
        + citation_score * 0.1
        + recency * 0.05
        + oa_bonus * 0.05
        - no_abstract_penalty
    )
    return round(max(0, score), 4)


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
            # Extract last name: handle "Last, First" and "First Last" formats
            if "," in first_author:
                # "Last, First" format
                authors_str = slugify(first_author.split(",")[0].strip())
            else:
                # "First Last" or "Last F." format - take first word that looks like a surname
                parts = first_author.split()
                if len(parts) >= 2:
                    # Take the part that's longer (likely the surname)
                    authors_str = slugify(parts[-2] if len(parts[-2]) > len(parts[-1]) else parts[-1])
                elif parts:
                    authors_str = slugify(parts[0])
    except Exception:
        pass

    year = paper.get("year") or "nd"
    title_words = slugify(paper.get("title", "")).split("-")
    short_title = title_words[0] if title_words else "untitled"

    if authors_str:
        return f"{authors_str}{year}{short_title}"
    return f"{year}{short_title}"
