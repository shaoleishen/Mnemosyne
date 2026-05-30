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

CREATE TABLE IF NOT EXISTS topic_aliases (
    alias TEXT PRIMARY KEY,
    canonical_topic TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_aliases (
    alias_type TEXT NOT NULL,
    alias_value TEXT NOT NULL,
    paper_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(alias_type, alias_value)
);

CREATE TABLE IF NOT EXISTS discovery_queries (
    query_id TEXT PRIMARY KEY,
    canonical_topic TEXT NOT NULL,
    raw_query TEXT NOT NULL,
    normalized_query TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    api_endpoint TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    cursor_token TEXT,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    paper_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    next_retry_at TEXT,
    started_at TEXT,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(canonical_topic, query_hash, api_endpoint, params_hash)
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
        "evidence_status": "TEXT DEFAULT 'abstract_only'",
        "source_quote": "TEXT",
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

    # Add indices for query performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_topic ON claims(topic)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_paper_id ON claims(paper_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_topic_papers_topic ON topic_papers(topic)")

    # Composite indexes for common query patterns
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_topic_type_conf ON claims(topic, evidence_type, confidence DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_topic_papers_topic_score ON topic_papers(topic, relevance_score DESC)")

    # Only create relevance_score index if the column exists
    cursor.execute("PRAGMA table_info(papers)")
    papers_cols = {row[1] for row in cursor.fetchall()}
    if "relevance_score" in papers_cols:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_relevance_score ON papers(relevance_score)")

    # Agent runs indexes
    cursor.execute("PRAGMA table_info(agent_runs)")
    ar_cols = {row[1] for row in cursor.fetchall()}
    if ar_cols:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_status_created ON agent_runs(status, created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_task_provider ON agent_runs(task_type, provider, status, created_at DESC)")

    # LLM runs indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_llm_runs_task_created ON llm_runs(task_type, created_at DESC)")

    # Paper aliases indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_paper_aliases_paper_id ON paper_aliases(paper_id)")

    # Discovery queries indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_discovery_queries_topic_status ON discovery_queries(canonical_topic, status, updated_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_discovery_queries_retry ON discovery_queries(status, next_retry_at)")

    # Idempotency index for claims
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_claims_idempotency ON claims(paper_id, topic, evidence_type, claim_hash)")

    conn.commit()


class Storage:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
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
        """Batch upsert papers in a single transaction."""
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for paper in papers:
            rows.append((
                paper.paper_id, paper.title, paper.abstract, paper.year, paper.publication_date,
                paper.venue, paper.url, paper.doi, paper.pmid, paper.arxiv_id,
                paper.citation_count, paper.reference_count, paper.influential_citation_count,
                paper.fields_json, paper.authors_json, paper.external_ids_json,
                paper.open_access_pdf_json, paper.discovered_by, paper.relevance_score,
                paper.created_at or now, now,
            ))
        self.conn.executemany(
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
            rows,
        )
        self.conn.commit()

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
        """Batch insert links in a single transaction."""
        now = datetime.now(timezone.utc).isoformat()
        rows = [(l.source_paper_id, l.target_paper_id, l.link_type, l.created_at or now) for l in links]
        self.conn.executemany(
            """INSERT OR IGNORE INTO paper_links (source_paper_id, target_paper_id, link_type, created_at)
            VALUES (?, ?, ?, ?)""",
            rows,
        )
        self.conn.commit()

    def insert_claim(self, claim: Claim) -> None:
        now = datetime.now(timezone.utc).isoformat()
        claim_hash = compute_claim_hash(claim)
        source_text_hash = hashlib.sha256((claim.source_quote or claim.claim_text).encode()).hexdigest()[:16]
        self.conn.execute(
            """INSERT OR REPLACE INTO claims (claim_id, paper_id, claim_text, evidence_type,
                confidence, source_location, topic, created_at,
                claim_hash, source_text_hash, source_span_json, extraction_method,
                is_placeholder, citation_key, evidence_status, source_quote)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (claim.claim_id, claim.paper_id, claim.claim_text, claim.evidence_type,
             claim.confidence, claim.source_location, claim.topic, claim.created_at or now,
             claim_hash, source_text_hash, claim.source_span_json, "deterministic",
             1 if claim.evidence_type == "full_text_needed" else 0,
             claim.citation_key, claim.evidence_status, claim.source_quote),
        )
        self.conn.commit()

    def insert_claims(self, claims: list[Claim]) -> None:
        """Batch insert claims in a single transaction."""
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for c in claims:
            claim_hash = compute_claim_hash(c)
            source_text_hash = hashlib.sha256((c.source_quote or c.claim_text).encode()).hexdigest()[:16]
            rows.append((
                c.claim_id, c.paper_id, c.claim_text, c.evidence_type,
                c.confidence, c.source_location, c.topic, c.created_at or now,
                claim_hash, source_text_hash, c.source_span_json, "deterministic",
                1 if c.evidence_type == "full_text_needed" else 0,
                c.citation_key, c.evidence_status, c.source_quote,
            ))
        self.conn.executemany(
            """INSERT OR REPLACE INTO claims (claim_id, paper_id, claim_text, evidence_type,
                confidence, source_location, topic, created_at,
                claim_hash, source_text_hash, source_span_json, extraction_method,
                is_placeholder, citation_key, evidence_status, source_quote)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self.conn.commit()

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
                claim_hash, source_text_hash, extraction_method, citation_key,
                source_span_json, is_placeholder, evidence_status, source_quote)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (claim.claim_id, claim.paper_id, claim.claim_text, claim.evidence_type,
             claim.confidence, claim.source_location, claim.topic, claim.created_at or now,
             claim_hash, hashlib.sha256((claim.source_quote or claim.claim_text).encode()).hexdigest()[:16],
             extraction_method, citation_key or claim.citation_key,
             source_span_json or claim.source_span_json, 1 if is_placeholder else 0,
             claim.evidence_status, claim.source_quote),
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
        """Batch insert topic papers in a single transaction."""
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for i, pid in enumerate(paper_ids):
            score = scores[i] if scores and i < len(scores) else 0.0
            rows.append((topic, pid, source, score, None, None, now, now))
        self.conn.executemany(
            """INSERT INTO topic_papers (topic, paper_id, source, relevance_score,
                llm_relevance_score, llm_relevance_reason, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic, paper_id) DO UPDATE SET
                source=excluded.source,
                relevance_score=excluded.relevance_score,
                llm_relevance_score=COALESCE(excluded.llm_relevance_score, topic_papers.llm_relevance_score),
                llm_relevance_reason=COALESCE(excluded.llm_relevance_reason, topic_papers.llm_relevance_reason),
                updated_at=excluded.updated_at""",
            rows,
        )
        self.conn.commit()

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

    def resolve_topic(self, topic: str) -> str:
        """Resolve a topic alias to its canonical topic.

        If the topic has no alias, returns the topic itself.
        Also checks if the topic is a substring of any existing topic_papers entry.
        """
        # Check direct alias
        row = self.conn.execute(
            "SELECT canonical_topic FROM topic_aliases WHERE alias = ?", (topic,)
        ).fetchone()
        if row:
            return row[0]

        # Check if topic is a canonical topic
        row = self.conn.execute(
            "SELECT COUNT(*) FROM topic_papers WHERE topic = ?", (topic,)
        ).fetchone()
        if row[0] > 0:
            return topic

        # Try substring matching: find topics that contain this topic or vice versa
        rows = self.conn.execute(
            "SELECT DISTINCT topic FROM topic_papers WHERE topic LIKE ? OR ? LIKE '%' || topic || '%'",
            (f"%{topic}%", topic),
        ).fetchall()
        if rows:
            # Return the shortest matching topic (most specific)
            topics = [r[0] for r in rows]
            return min(topics, key=len)

        return topic

    def add_topic_alias(self, alias: str, canonical_topic: str) -> None:
        """Add a topic alias mapping."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO topic_aliases (alias, canonical_topic, created_at)
            VALUES (?, ?, ?)""",
            (alias, canonical_topic, now),
        )
        self.conn.commit()

    def get_canonical_topics(self) -> list[str]:
        """Get all canonical topics that have papers."""
        rows = self.conn.execute(
            "SELECT DISTINCT topic FROM topic_papers ORDER BY topic"
        ).fetchall()
        return [r[0] for r in rows]

    def get_topic_aliases(self, canonical_topic: str) -> list[str]:
        """Get all aliases for a canonical topic."""
        rows = self.conn.execute(
            "SELECT alias FROM topic_aliases WHERE canonical_topic = ?",
            (canonical_topic,),
        ).fetchall()
        return [r[0] for r in rows]

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

    # --- Paper Aliases ---

    def insert_paper_alias(self, alias_type: str, alias_value: str, paper_id: str) -> None:
        """Insert a paper alias for cross-run deduplication."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR IGNORE INTO paper_aliases (alias_type, alias_value, paper_id, created_at)
            VALUES (?, ?, ?, ?)""",
            (alias_type, alias_value, paper_id, now),
        )
        self.conn.commit()

    def insert_paper_aliases(self, aliases: list[tuple[str, str, str]]) -> None:
        """Batch insert paper aliases. Each tuple is (alias_type, alias_value, paper_id)."""
        now = datetime.now(timezone.utc).isoformat()
        rows = [(a[0], a[1], a[2], now) for a in aliases]
        self.conn.executemany(
            """INSERT OR IGNORE INTO paper_aliases (alias_type, alias_value, paper_id, created_at)
            VALUES (?, ?, ?, ?)""",
            rows,
        )
        self.conn.commit()

    def find_paper_by_alias(self, alias_type: str, alias_value: str) -> str | None:
        """Find a paper_id by alias. Returns None if not found."""
        row = self.conn.execute(
            "SELECT paper_id FROM paper_aliases WHERE alias_type = ? AND alias_value = ?",
            (alias_type, alias_value),
        ).fetchone()
        return row[0] if row else None

    def get_paper_aliases(self, paper_id: str) -> list[dict[str, str]]:
        """Get all aliases for a paper."""
        rows = self.conn.execute(
            "SELECT alias_type, alias_value FROM paper_aliases WHERE paper_id = ?",
            (paper_id,),
        ).fetchall()
        return [{"alias_type": r[0], "alias_value": r[1]} for r in rows]

    # --- Discovery Queries ---

    def upsert_discovery_query(self, query_id: str, canonical_topic: str, raw_query: str,
                                normalized_query: str, query_hash: str, api_endpoint: str,
                                params_hash: str, status: str = "planned",
                                cursor_token: str | None = None) -> None:
        """Insert or update a discovery query ledger entry."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO discovery_queries (query_id, canonical_topic, raw_query, normalized_query,
                query_hash, api_endpoint, params_hash, cursor_token, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_topic, query_hash, api_endpoint, params_hash) DO UPDATE SET
                status=CASE WHEN discovery_queries.status='completed' THEN discovery_queries.status ELSE excluded.status END,
                cursor_token=COALESCE(excluded.cursor_token, discovery_queries.cursor_token),
                updated_at=excluded.updated_at""",
            (query_id, canonical_topic, raw_query, normalized_query, query_hash,
             api_endpoint, params_hash, cursor_token, status, now),
        )
        self.conn.commit()

    def update_discovery_query_status(self, query_id: str, status: str,
                                       cursor_token: str | None = None,
                                       paper_count: int | None = None,
                                       error: str | None = None,
                                       next_retry_at: str | None = None) -> None:
        """Update a discovery query's status and metadata."""
        now = datetime.now(timezone.utc).isoformat()
        completed_at = now if status == "completed" else None
        self.conn.execute(
            """UPDATE discovery_queries SET
                status = ?, cursor_token = COALESCE(?, cursor_token),
                paper_count = COALESCE(?, paper_count), last_error = COALESCE(?, last_error),
                next_retry_at = COALESCE(?, next_retry_at),
                attempts = attempts + 1, updated_at = ?, completed_at = COALESCE(?, completed_at)
            WHERE query_id = ?""",
            (status, cursor_token, paper_count, error, next_retry_at, now, completed_at, query_id),
        )
        self.conn.commit()

    def get_discovery_query(self, canonical_topic: str, query_hash: str,
                             api_endpoint: str, params_hash: str) -> dict[str, Any] | None:
        """Get a discovery query by its fingerprint."""
        row = self.conn.execute(
            """SELECT * FROM discovery_queries
            WHERE canonical_topic = ? AND query_hash = ? AND api_endpoint = ? AND params_hash = ?""",
            (canonical_topic, query_hash, api_endpoint, params_hash),
        ).fetchone()
        return dict(row) if row else None

    def get_discovery_queries_by_topic(self, canonical_topic: str) -> list[dict[str, Any]]:
        """Get all discovery queries for a topic."""
        rows = self.conn.execute(
            "SELECT * FROM discovery_queries WHERE canonical_topic = ? ORDER BY updated_at DESC",
            (canonical_topic,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_discovery_topic_coverage(self, canonical_topic: str) -> dict[str, Any]:
        """Get coverage summary for a topic."""
        rows = self.conn.execute(
            """SELECT status, COUNT(*) as cnt, SUM(paper_count) as total_papers
            FROM discovery_queries WHERE canonical_topic = ?
            GROUP BY status""",
            (canonical_topic,),
        ).fetchall()
        coverage = {"total_queries": 0, "total_papers": 0, "by_status": {}}
        for r in rows:
            coverage["by_status"][r[0]] = {"count": r[1], "papers": r[2] or 0}
            coverage["total_queries"] += r[1]
            coverage["total_papers"] += r[2] or 0
        return coverage


def compute_claim_hash(claim: Claim) -> str:
    """Compute a deterministic hash for a claim based on its content."""
    normalized = " ".join(claim.claim_text.lower().split())
    raw = f"{claim.paper_id}:{claim.topic or ''}:{claim.evidence_type}:{normalized}:{claim.source_location}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
