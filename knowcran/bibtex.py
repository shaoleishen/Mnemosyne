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
        authors = " and ".join(_escape_bibtex(a.get("name", "")) for a in authors_list[:5])
    except Exception:
        pass

    title = _escape_bibtex(paper.get("title", "") or "")
    year = paper.get("year") or ""
    journal = _escape_bibtex(paper.get("venue", "") or "")
    doi = paper.get("doi") or ""

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
        lines.append(f"  doi = {{{doi}}}")
    lines.append("}")
    return "\n".join(lines)


def papers_to_bibtex(papers: list[dict[str, Any]]) -> str:
    return "\n\n".join(paper_to_bibtex(p) for p in papers) + "\n"
