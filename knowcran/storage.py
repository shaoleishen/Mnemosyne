"""SQLite storage layer for KnowCran."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowcran.config import DB_PATH, DATA_DIR
from knowcran.models import Claim, PaperLink, PaperRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    paper_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    abstract TEXT,
    year INTEGER,
    publication_date TEXT,
    venue TEXT,
    url TEXT,
    doi TEXT,
    pmid TEXT,
    arxiv_id TEXT,
    citation_count INTEGER,
    reference_count INTEGER,
    influential_citation_count INTEGER,
    fields_json TEXT,
    authors_json TEXT,
    external_ids_json TEXT,
    open_access_pdf_json TEXT,
    discovered_by TEXT,
    relevance_score REAL,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS paper_links (
    source_paper_id TEXT,
    target_paper_id TEXT,
    link_type TEXT,
    created_at TEXT,
    PRIMARY KEY(source_paper_id, target_paper_id, link_type)
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    evidence_type TEXT,
    confidence REAL,
    source_location TEXT,
    topic TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS topic_papers (
    topic TEXT,
    paper_id TEXT,
    source TEXT,
    relevance_score REAL,
    created_at TEXT,
    PRIMARY KEY(topic, paper_id)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    command TEXT,
    query TEXT,
    params_json TEXT,
    created_at TEXT
);
"""


class Storage:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def upsert_paper(self, paper: PaperRecord) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO papers (paper_id, title, abstract, year, publication_date, venue, url,
                doi, pmid, arxiv_id, citation_count, reference_count, influential_citation_count,
                fields_json, authors_json, external_ids_json, open_access_pdf_json,
                discovered_by, relevance_score, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id) DO UPDATE SET
                title=excluded.title, abstract=excluded.abstract, year=excluded.year,
                publication_date=excluded.publication_date, venue=excluded.venue, url=excluded.url,
                doi=excluded.doi, pmid=excluded.pmid, arxiv_id=excluded.arxiv_id,
                citation_count=excluded.citation_count, reference_count=excluded.reference_count,
                influential_citation_count=excluded.influential_citation_count,
                fields_json=excluded.fields_json, authors_json=excluded.authors_json,
                external_ids_json=excluded.external_ids_json, open_access_pdf_json=excluded.open_access_pdf_json,
                discovered_by=excluded.discovered_by, relevance_score=excluded.relevance_score,
                updated_at=excluded.updated_at""",
            (paper.paper_id, paper.title, paper.abstract, paper.year, paper.publication_date,
             paper.venue, paper.url, paper.doi, paper.pmid, paper.arxiv_id,
             paper.citation_count, paper.reference_count, paper.influential_citation_count,
             paper.fields_json, paper.authors_json, paper.external_ids_json,
             paper.open_access_pdf_json, paper.discovered_by, paper.relevance_score,
             paper.created_at or now, now),
        )
        self.conn.commit()

    def upsert_papers(self, papers: list[PaperRecord]) -> None:
        for p in papers:
            self.upsert_paper(p)

    def get_paper(self, paper_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
        return dict(row) if row else None

    def get_papers_by_topic(self, topic: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM papers WHERE title LIKE ? OR abstract LIKE ? ORDER BY relevance_score DESC LIMIT ?",
            (f"%{topic}%", f"%{topic}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def insert_link(self, link: PaperLink) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR IGNORE INTO paper_links (source_paper_id, target_paper_id, link_type, created_at)
            VALUES (?, ?, ?, ?)""",
            (link.source_paper_id, link.target_paper_id, link.link_type, link.created_at or now),
        )
        self.conn.commit()

    def insert_links(self, links: list[PaperLink]) -> None:
        for l in links:
            self.insert_link(l)

    def insert_claim(self, claim: Claim) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO claims (claim_id, paper_id, claim_text, evidence_type,
                confidence, source_location, topic, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (claim.claim_id, claim.paper_id, claim.claim_text, claim.evidence_type,
             claim.confidence, claim.source_location, claim.topic, claim.created_at or now),
        )
        self.conn.commit()

    def insert_claims(self, claims: list[Claim]) -> None:
        for c in claims:
            self.insert_claim(c)

    def get_claims_by_topic(self, topic: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM claims WHERE topic = ? ORDER BY evidence_type, confidence DESC",
            (topic,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_claims_for_paper(self, paper_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM claims WHERE paper_id = ?", (paper_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_links(self, paper_id: str, link_type: str | None = None) -> list[dict[str, Any]]:
        if link_type:
            rows = self.conn.execute(
                "SELECT * FROM paper_links WHERE source_paper_id = ? AND link_type = ?",
                (paper_id, link_type),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM paper_links WHERE source_paper_id = ?", (paper_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def insert_run(self, run_id: str, command: str, query: str, params_json: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO runs (run_id, command, query, params_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (run_id, command, query, params_json, now),
        )
        self.conn.commit()

    def count_papers(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]

    def count_claims(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]

    def count_links(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM paper_links").fetchone()[0]

    def insert_topic_paper(self, topic: str, paper_id: str, source: str = "discover", relevance_score: float = 0.0) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO topic_papers (topic, paper_id, source, relevance_score, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            (topic, paper_id, source, relevance_score, now),
        )
        self.conn.commit()

    def insert_topic_papers(self, topic: str, paper_ids: list[str], source: str = "discover", scores: list[float] | None = None) -> None:
        for i, pid in enumerate(paper_ids):
            score = scores[i] if scores and i < len(scores) else 0.0
            self.insert_topic_paper(topic, pid, source, score)

    def get_topic_papers(self, topic: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT p.* FROM papers p
            INNER JOIN topic_papers tp ON p.paper_id = tp.paper_id
            WHERE tp.topic = ?
            ORDER BY tp.relevance_score DESC, p.relevance_score DESC
            LIMIT ?""",
            (topic, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def has_topic_papers(self, topic: str) -> bool:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM topic_papers WHERE topic = ?", (topic,)
        ).fetchone()
        return row[0] > 0
