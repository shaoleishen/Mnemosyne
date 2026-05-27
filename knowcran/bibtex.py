"""BibTeX generation from stored papers."""

from __future__ import annotations

import json
from typing import Any

from knowcran.utils import citation_key


def paper_to_bibtex(paper: dict[str, Any]) -> str:
    key = citation_key(paper)
    authors = ""
    try:
        authors_list = json.loads(paper.get("authors_json") or "[]")
        authors = " and ".join(a.get("name", "") for a in authors_list[:5])
    except Exception:
        pass
    return f"""@article{{{key},
  title = {{{paper.get('title', '')}}},
  author = {{{authors}}},
  year = {{{paper.get('year', '')}}},
  journal = {{{paper.get('venue', '')}}},
  doi = {{{paper.get('doi', '')}}}
}}"""


def papers_to_bibtex(papers: list[dict[str, Any]]) -> str:
    return "\n\n".join(paper_to_bibtex(p) for p in papers) + "\n"
