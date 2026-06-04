"""Tests for BibTeX generation and Obsidian export improvements."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowcran.bibtex import paper_to_bibtex, papers_to_bibtex
from knowcran.models import Claim, PaperRecord
from knowcran.obsidian import _paper_note, _claim_note, export_obsidian
from knowcran.storage import Storage
from knowcran.utils import citation_key


class TestBibTeX:
    def test_basic_paper_to_bibtex(self):
        paper = {
            "paper_id": "p1",
            "title": "ICH Outcomes Study",
            "year": 2023,
            "venue": "Stroke",
            "doi": "10.1234/test",
            "authors_json": '[{"name": "Smith, J."}]',
        }
        bib = paper_to_bibtex(paper)
        assert "@article{" in bib
        assert "Smith, J." in bib
        assert "ICH Outcomes Study" in bib
        assert "doi = {10.1234/test}" in bib

    def test_missing_doi_omitted(self):
        paper = {
            "paper_id": "p1",
            "title": "Test Paper",
            "year": 2023,
            "doi": None,
            "authors_json": "[]",
        }
        bib = paper_to_bibtex(paper)
        assert "doi" not in bib

    def test_none_string_doi_omitted(self):
        paper = {
            "paper_id": "p1",
            "title": "Test Paper",
            "year": 2023,
            "doi": "None",
            "authors_json": "[]",
        }
        bib = paper_to_bibtex(paper)
        assert "doi" not in bib

    def test_hyphenated_author_names(self):
        paper = {
            "paper_id": "p1",
            "title": "Test",
            "authors_json": '[{"name": "van der Berg, J."}, {"name": "Smith-Jones, A."}]',
        }
        bib = paper_to_bibtex(paper)
        assert "van der Berg, J." in bib
        assert "Smith-Jones, A." in bib

    def test_missing_authors_handled(self):
        paper = {
            "paper_id": "p1",
            "title": "Test Paper",
            "authors_json": None,
        }
        bib = paper_to_bibtex(paper)
        assert "author" not in bib

    def test_empty_authors_json(self):
        paper = {
            "paper_id": "p1",
            "title": "Test Paper",
            "authors_json": "[]",
        }
        bib = paper_to_bibtex(paper)
        assert "author" not in bib

    def test_special_chars_escaped(self):
        paper = {
            "paper_id": "p1",
            "title": "Effects of 50% & More",
            "authors_json": '[{"name": "O\'Brien, C."}]',
        }
        bib = paper_to_bibtex(paper)
        assert "\\&" in bib
        assert "\\%" in bib

    def test_url_included(self):
        paper = {
            "paper_id": "p1",
            "title": "Test",
            "url": "https://example.com/paper",
            "authors_json": "[]",
        }
        bib = paper_to_bibtex(paper)
        assert "url = {https://example.com/paper}" in bib

    def test_no_trailing_comma_on_last_field(self):
        paper = {
            "paper_id": "p1",
            "title": "Test",
            "authors_json": "[]",
        }
        bib = paper_to_bibtex(paper)
        lines = bib.split("\n")
        # Last field before closing } should not have trailing comma
        for i, line in enumerate(lines):
            if line.strip() == "}":
                if i > 0:
                    prev = lines[i - 1].strip()
                    assert not prev.endswith(","), f"Trailing comma: {prev}"


class TestObsidianExport:
    def test_paper_note_has_citation_key(self):
        paper = {
            "paper_id": "p1",
            "title": "ICH Study",
            "year": 2023,
            "venue": "Stroke",
        }
        note = _paper_note(paper, [], [], citation_key="Smith2023ich")
        assert 'citation_key: "Smith2023ich"' in note

    def test_claim_note_has_extraction_method(self):
        claim = {
            "claim_id": "c1",
            "paper_id": "p1",
            "evidence_type": "result",
            "confidence": 0.8,
            "claim_text": "ICH has high mortality",
            "extraction_method": "claw",
        }
        note = _claim_note(claim)
        assert "extraction_method: claw" in note

    def test_claim_note_default_extraction_method(self):
        claim = {
            "claim_id": "c1",
            "paper_id": "p1",
            "evidence_type": "result",
            "confidence": 0.8,
            "claim_text": "ICH has high mortality",
        }
        note = _claim_note(claim)
        assert "extraction_method: deterministic" in note

    def test_paper_note_has_abstract(self):
        paper = {
            "paper_id": "p1",
            "title": "ICH Study",
            "abstract": "ICH is a devastating stroke subtype.",
        }
        note = _paper_note(paper, [], [], citation_key="Test2023")
        assert "ICH is a devastating stroke subtype." in note

    def test_claim_note_links_to_paper(self):
        claim = {
            "claim_id": "c1",
            "paper_id": "p1",
            "evidence_type": "result",
            "confidence": 0.8,
            "claim_text": "High mortality",
        }
        note_map = {"p1": "2023_ich-study"}
        note = _claim_note(claim, note_map)
        assert "[[2023_ich-study]]" in note


class TestBibTeXAuthors:
    def test_authors_present_when_available(self):
        paper = {
            "paper_id": "p1",
            "title": "Test",
            "authors_json": '[{"name": "Wang, L."}, {"name": "Zhang, Y."}]',
        }
        bib = paper_to_bibtex(paper)
        assert "author = {Wang, L. and Zhang, Y.}" in bib

    def test_max_five_authors(self):
        paper = {
            "paper_id": "p1",
            "title": "Test",
            "authors_json": json.dumps([{"name": f"Author{i}"} for i in range(10)]),
        }
        bib = paper_to_bibtex(paper)
        assert "Author0 and Author1 and Author2 and Author3 and Author4" in bib
        assert "Author5" not in bib
