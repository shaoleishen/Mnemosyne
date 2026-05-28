"""SQLite storage layer for KnowCran."""

from __future__ import annotations

import hashlib
import json
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
    created_at TEXT,
    claim_hash TEXT,
    source_text_hash TEXT,
    source_span_json TEXT,
    extraction_method TEXT DEFAULT 'deterministic',
    is_placeholder INTEGER DEFAULT 0,
    citation_key TEXT
);

CREATE TABLE IF NOT EXISTS topic_papers (
    topic TEXT,
    paper_id TEXT,
    source TEXT,
    relevance_score REAL,
    llm_relevance_score REAL,
    llm_relevance_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(topic, paper_id)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    command TEXT,
    query TEXT,
    params_json TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS llm_runs (
    run_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT,
    task_type TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    prompt_json TEXT,
    raw_output TEXT,
    parsed_output_json TEXT,
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    provider_mode TEXT NOT NULL,
    model TEXT,
    task_type TEXT NOT NULL,
    task_id TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    input_json TEXT,
    output_schema_name TEXT,
    raw_output TEXT,
    parsed_output_json TEXT,
    status TEXT NOT NULL,
    error TEXT,
    usage_json TEXT,
    created_at TEXT NOT NULL
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply idempotent schema migrations for existing databases."""
    cursor = conn.cursor()

    # Get existing columns for claims table
    cursor.execute("PRAGMA table_info(claims)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    # Add missing columns to claims
    new_cols = {
        "claim_hash": "TEXT",
        "source_text_hash": "TEXT",
        "source_span_json": "TEXT",
        "extraction_method": "TEXT DEFAULT 'deterministic'",
        "is_placeholder": "INTEGER DEFAULT 0",
        "citation_key": "TEXT",
    }
    for col, col_type in new_cols.items():
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE claims ADD COLUMN {col} {col_type}")

    # Get existing columns for topic_papers table
    cursor.execute("PRAGMA table_info(topic_papers)")
    tp_cols = {row[1] for row in cursor.fetchall()}

    if "llm_relevance_score" not in tp_cols:
        cursor.execute("ALTER TABLE topic_papers ADD COLUMN llm_relevance_score REAL")
    if "llm_relevance_reason" not in tp_cols:
        cursor.execute("ALTER TABLE topic_papers ADD COLUMN llm_relevance_reason TEXT")
    if "updated_at" not in tp_cols:
        cursor.execute("ALTER TABLE topic_papers ADD COLUMN updated_at TEXT")
        cursor.execute("UPDATE topic_papers SET updated_at = created_at WHERE updated_at IS NULL")

    conn.commit()


class Storage:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_SCHEMA)
        _migrate(self.conn)

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

    def upsert_claim_idempotent(self, claim: Claim, extraction_method: str = "deterministic",
                                 citation_key: str | None = None,
                                 source_span_json: str | None = None,
                                 is_placeholder: bool = False) -> bool:
        """Insert a claim only if it doesn't already exist (idempotent).

        Returns True if inserted, False if already exists.
        """
        now = datetime.now(timezone.utc).isoformat()
        claim_hash = compute_claim_hash(claim)
        existing = self.conn.execute(
            "SELECT claim_id FROM claims WHERE claim_hash = ? AND paper_id = ? AND topic = ?",
            (claim_hash, claim.paper_id, claim.topic),
        ).fetchone()
        if existing:
            return False

        self.conn.execute(
            """INSERT INTO claims (claim_id, paper_id, claim_text, evidence_type,
                confidence, source_location, topic, created_at,
                claim_hash, extraction_method, citation_key, source_span_json, is_placeholder)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (claim.claim_id, claim.paper_id, claim.claim_text, claim.evidence_type,
             claim.confidence, claim.source_location, claim.topic, claim.created_at or now,
             claim_hash, extraction_method, citation_key, source_span_json, 1 if is_placeholder else 0),
        )
        self.conn.commit()
        return True

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

    def insert_topic_paper(self, topic: str, paper_id: str, source: str = "discover",
                           relevance_score: float = 0.0,
                           llm_relevance_score: float | None = None,
                           llm_relevance_reason: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO topic_papers (topic, paper_id, source, relevance_score,
                llm_relevance_score, llm_relevance_reason, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic, paper_id) DO UPDATE SET
                source=excluded.source,
                relevance_score=excluded.relevance_score,
                llm_relevance_score=COALESCE(excluded.llm_relevance_score, topic_papers.llm_relevance_score),
                llm_relevance_reason=COALESCE(excluded.llm_relevance_reason, topic_papers.llm_relevance_reason),
                updated_at=excluded.updated_at""",
            (topic, paper_id, source, relevance_score, llm_relevance_score, llm_relevance_reason, now, now),
        )
        self.conn.commit()

    def insert_topic_papers(self, topic: str, paper_ids: list[str], source: str = "discover",
                            scores: list[float] | None = None) -> None:
        for i, pid in enumerate(paper_ids):
            score = scores[i] if scores and i < len(scores) else 0.0
            self.insert_topic_paper(topic, pid, source, score)

    def get_topic_papers(self, topic: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT p.* FROM papers p
            INNER JOIN topic_papers tp ON p.paper_id = tp.paper_id
            WHERE tp.topic = ?
            ORDER BY COALESCE(tp.llm_relevance_score, tp.relevance_score) DESC, p.relevance_score DESC
            LIMIT ?""",
            (topic, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def has_topic_papers(self, topic: str) -> bool:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM topic_papers WHERE topic = ?", (topic,)
        ).fetchone()
        return row[0] > 0

    # --- LLM Runs ---

    def insert_llm_run(self, run_id: str, provider: str, task_type: str, input_hash: str,
                       model: str | None = None, prompt_json: str | None = None,
                       raw_output: str | None = None, parsed_output_json: str | None = None,
                       status: str = "pending", error: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO llm_runs (run_id, provider, model, task_type, input_hash,
                prompt_json, raw_output, parsed_output_json, status, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, provider, model, task_type, input_hash,
             prompt_json, raw_output, parsed_output_json, status, error, now),
        )
        self.conn.commit()

    def update_llm_run(self, run_id: str, status: str, raw_output: str | None = None,
                       parsed_output_json: str | None = None, error: str | None = None) -> None:
        self.conn.execute(
            """UPDATE llm_runs SET status = ?, raw_output = COALESCE(?, raw_output),
                parsed_output_json = COALESCE(?, parsed_output_json), error = COALESCE(?, error)
            WHERE run_id = ?""",
            (status, raw_output, parsed_output_json, error, run_id),
        )
        self.conn.commit()

    def get_llm_runs(self, task_type: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if task_type:
            rows = self.conn.execute(
                "SELECT * FROM llm_runs WHERE task_type = ? ORDER BY created_at DESC LIMIT ?",
                (task_type, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM llm_runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Agent Runs ---

    def insert_agent_run(self, run_id: str, provider: str, provider_mode: str,
                         task_type: str, task_id: str, input_hash: str,
                         model: str | None = None, input_json: str | None = None,
                         output_schema_name: str | None = None,
                         raw_output: str | None = None, parsed_output_json: str | None = None,
                         status: str = "pending", error: str | None = None,
                         usage_json: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO agent_runs (run_id, provider, provider_mode, model, task_type, task_id,
                input_hash, input_json, output_schema_name, raw_output, parsed_output_json,
                status, error, usage_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, provider, provider_mode, model, task_type, task_id,
             input_hash, input_json, output_schema_name, raw_output, parsed_output_json,
             status, error, usage_json, now),
        )
        self.conn.commit()

    def update_agent_run(self, run_id: str, status: str, raw_output: str | None = None,
                         parsed_output_json: str | None = None, error: str | None = None,
                         usage_json: str | None = None) -> None:
        self.conn.execute(
            """UPDATE agent_runs SET status = ?, raw_output = COALESCE(?, raw_output),
                parsed_output_json = COALESCE(?, parsed_output_json), error = COALESCE(?, error),
                usage_json = COALESCE(?, usage_json)
            WHERE run_id = ?""",
            (status, raw_output, parsed_output_json, error, usage_json, run_id),
        )
        self.conn.commit()

    def get_agent_runs(self, task_type: str | None = None, provider: str | None = None,
                       status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        conditions = []
        params: list[Any] = []
        if task_type:
            conditions.append("task_type = ?")
            params.append(task_type)
        if provider:
            conditions.append("provider = ?")
            params.append(provider)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(limit)

        rows = self.conn.execute(
            f"SELECT * FROM agent_runs{where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def get_agent_run_failures(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.get_agent_runs(status="error", limit=limit)


def compute_claim_hash(claim: Claim) -> str:
    """Compute a deterministic hash for a claim based on its content."""
    normalized = " ".join(claim.claim_text.lower().split())
    raw = f"{claim.paper_id}:{claim.topic or ''}:{claim.evidence_type}:{normalized}:{claim.source_location}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
