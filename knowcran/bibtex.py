"""BibTeX generation from stored papers."""

from __future__ import annotations

import json
import re
from typing import Any

from knowcran.utils import citation_key

# Characters that need escaping in BibTeX
_BIBTEX_SPECIAL = re.compile(r"[#\$%\&\\^_\{}\~]")


def _escape_bibtex(text: str) -> str:
    """Escape special BibTeX characters."""
    return _BIBTEX_SPECIAL.sub(lambda m: f"\\{m.group()}", text)


def paper_to_bibtex(paper: dict[str, Any]) -> str:
    key = citation_key(paper)
    authors = ""
    try:
        authors_list = json.loads(paper.get("authors_json") or "[]")
        if authors_list:
            names = []
            for a in authors_list[:5]:
                name = a.get("name", "").strip()
                if name:
                    names.append(_escape_bibtex(name))
            authors = " and ".join(names)
    except (json.JSONDecodeError, TypeError):
        pass

    title = _escape_bibtex(paper.get("title", "") or "")
    year = paper.get("year") or ""
    journal = _escape_bibtex(paper.get("venue", "") or "")
    doi = paper.get("doi") or ""
    # Don't write "None" as a DOI string
    if doi.lower() in ("none", "null"):
        doi = ""
    url = paper.get("url") or ""

    lines = [f"@article{{{key},"]
    if title:
        lines.append(f"  title = {{{title}}},")
    if authors:
        lines.append(f"  author = {{{authors}}},")
    if year:
        lines.append(f"  year = {{{year}}},")
    if journal:
        lines.append(f"  journal = {{{journal}}},")
    if doi:
        lines.append(f"  doi = {{{doi}}},")
    if url:
        lines.append(f"  url = {{{url}}}")
    # Remove trailing comma from last field
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.append("}")
    return "\n".join(lines)


def papers_to_bibtex(papers: list[dict[str, Any]]) -> str:
    return "\n\n".join(paper_to_bibtex(p) for p in papers) + "\n"
