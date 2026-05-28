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

    # Tangential/distractor penalty: high citation but low topic relevance
    tangential_penalty = 0.0
    if citation_count and citation_count > 500 and title_overlap < 0.3 and exact_title_boost == 0:
        tangential_penalty = 0.2

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
        - tangential_penalty
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


def classify_topic_role(title: str, abstract: str, topic: str) -> str:
    """Classify a paper's role relative to a topic.

    Returns one of:
    - primary_topic: topic is the main subject
    - secondary_topic: topic is a significant secondary subject
    - risk_or_complication: topic appears as a risk/complication/outcome
    - mentions_only: topic is only briefly mentioned
    - irrelevant: topic not found
    """
    title_lower = (title or "").lower()
    abstract_lower = (abstract or "").lower()
    topic_lower = topic.lower()

    # Count topic occurrences
    title_count = title_lower.count(topic_lower)
    abstract_count = abstract_lower.count(topic_lower)

    # Check if topic words appear in title
    topic_words = set(topic_lower.split())
    title_word_hits = sum(1 for w in topic_words if w in title_lower)

    # Primary: topic is in title and appears multiple times in abstract
    if title_count > 0 and abstract_count >= 2:
        return "primary_topic"

    # Primary: topic words dominate the title
    if title_word_hits >= len(topic_words) * 0.7 and abstract_count >= 1:
        return "primary_topic"

    # Secondary: topic appears in abstract but not title, or appears moderately
    if abstract_count >= 3:
        return "secondary_topic"

    # Risk/complication: topic appears 1-2 times in abstract, often with risk/complication language
    risk_terms = {"risk", "complication", "outcome", "adverse", "associated", "mortality", "morbidity"}
    if abstract_count >= 1:
        has_risk_context = any(t in abstract_lower for t in risk_terms)
        if has_risk_context and abstract_count <= 2:
            return "risk_or_complication"
        if abstract_count >= 2:
            return "secondary_topic"
        return "mentions_only"

    # Title mentions but abstract doesn't elaborate
    if title_count > 0:
        return "mentions_only"

    return "irrelevant"


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
