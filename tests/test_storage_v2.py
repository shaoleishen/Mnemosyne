"""Tests for storage refactor: topic_papers, llm_runs, claim idempotency."""

from __future__ import annotations

from pathlib import Path

import pytest

from knowcran.models import Claim, PaperRecord
from knowcran.storage import Storage, compute_claim_hash


@pytest.fixture
def storage(tmp_path):
    db = tmp_path / "test.sqlite"
    s = Storage(db_path=db)
    yield s
    s.close()


@pytest.fixture
def sample_paper_record():
    return PaperRecord(
        paper_id="paper1",
        title="Intracerebral Hemorrhage Outcomes",
        abstract="ICH is a devastating stroke subtype with high mortality.",
        year=2023,
        venue="Stroke",
        doi="10.1234/test",
        authors_json='[{"name": "Smith, J."}]',
    )


@pytest.fixture
def sample_claim():
    return Claim(
        claim_id="claim1",
        paper_id="paper1",
        claim_text="ICH has high mortality rates",
        evidence_type="result",
        confidence=0.8,
        source_location="abstract",
        topic="intracerebral hemorrhage",
    )


class TestTopicPapers:
    def test_insert_and_get_topic_paper(self, storage, sample_paper_record):
        storage.upsert_paper(sample_paper_record)
        storage.insert_topic_paper("ICH", "paper1", source="discover", relevance_score=0.9)
        papers = storage.get_topic_papers("ICH")
        assert len(papers) == 1
        assert papers[0]["paper_id"] == "paper1"

    def test_topic_papers_order_by_score(self, storage):
        p1 = PaperRecord(paper_id="p1", title="Paper One", relevance_score=0.5)
        p2 = PaperRecord(paper_id="p2", title="Paper Two", relevance_score=0.9)
        storage.upsert_papers([p1, p2])
        storage.insert_topic_paper("topic", "p1", relevance_score=0.5)
        storage.insert_topic_paper("topic", "p2", relevance_score=0.9)
        papers = storage.get_topic_papers("topic")
        assert papers[0]["paper_id"] == "p2"

    def test_has_topic_papers(self, storage, sample_paper_record):
        storage.upsert_paper(sample_paper_record)
        assert storage.has_topic_papers("ICH") is False
        storage.insert_topic_paper("ICH", "paper1")
        assert storage.has_topic_papers("ICH") is True

    def test_topic_papers_llm_scores(self, storage, sample_paper_record):
        storage.upsert_paper(sample_paper_record)
        storage.insert_topic_paper("ICH", "paper1", source="discover",
                                    relevance_score=0.7,
                                    llm_relevance_score=0.95,
                                    llm_relevance_reason="Directly studies ICH")
        papers = storage.get_topic_papers("ICH")
        assert len(papers) == 1

    def test_topic_papers_upsert_updates(self, storage, sample_paper_record):
        storage.upsert_paper(sample_paper_record)
        storage.insert_topic_paper("ICH", "paper1", relevance_score=0.5)
        storage.insert_topic_paper("ICH", "paper1", relevance_score=0.8,
                                    llm_relevance_score=0.9,
                                    llm_relevance_reason="Very relevant")
        papers = storage.get_topic_papers("ICH")
        assert len(papers) == 1


class TestLlmRuns:
    def test_insert_and_get_llm_run(self, storage):
        storage.insert_llm_run(
            run_id="run1",
            provider="claw",
            model="sonnet",
            task_type="extraction",
            input_hash="abc123",
            status="completed",
        )
        runs = storage.get_llm_runs(task_type="extraction")
        assert len(runs) == 1
        assert runs[0]["run_id"] == "run1"
        assert runs[0]["provider"] == "claw"

    def test_update_llm_run(self, storage):
        storage.insert_llm_run(
            run_id="run2",
            provider="claw",
            model=None,
            task_type="rerank",
            input_hash="def456",
            status="pending",
        )
        storage.update_llm_run("run2", status="completed", raw_output='{"ok": true}')
        runs = storage.get_llm_runs()
        assert runs[0]["status"] == "completed"

    def test_llm_runs_filter_by_task_type(self, storage):
        storage.insert_llm_run(run_id="r1", provider="claw", model=None, task_type="extraction", input_hash="h1", status="ok")
        storage.insert_llm_run(run_id="r2", provider="claw", model=None, task_type="rerank", input_hash="h2", status="ok")
        assert len(storage.get_llm_runs(task_type="extraction")) == 1
        assert len(storage.get_llm_runs(task_type="rerank")) == 1
        assert len(storage.get_llm_runs()) == 2


class TestClaimIdempotency:
    def test_upsert_idempotent_inserts_new(self, storage, sample_claim):
        inserted = storage.upsert_claim_idempotent(sample_claim, extraction_method="deterministic")
        assert inserted is True
        claims = storage.get_claims_by_topic("intracerebral hemorrhage")
        assert len(claims) == 1

    def test_upsert_idempotent_skips_duplicate(self, storage, sample_claim):
        storage.upsert_claim_idempotent(sample_claim)
        inserted = storage.upsert_claim_idempotent(sample_claim)
        assert inserted is False
        claims = storage.get_claims_by_topic("intracerebral hemorrhage")
        assert len(claims) == 1

    def test_compute_claim_hash_deterministic(self, sample_claim):
        h1 = compute_claim_hash(sample_claim)
        h2 = compute_claim_hash(sample_claim)
        assert h1 == h2

    def test_compute_claim_hash_different_claims(self):
        c1 = Claim(claim_id="a", paper_id="p1", claim_text="Result A", evidence_type="result", topic="t")
        c2 = Claim(claim_id="b", paper_id="p1", claim_text="Result B", evidence_type="result", topic="t")
        assert compute_claim_hash(c1) != compute_claim_hash(c2)

    def test_claim_with_extraction_method_stored(self, storage, sample_claim):
        storage.upsert_claim_idempotent(sample_claim, extraction_method="claw", citation_key="Smith2023")
        claims = storage.get_claims_for_paper("paper1")
        assert claims[0]["extraction_method"] == "claw"
        assert claims[0]["citation_key"] == "Smith2023"

    def test_repeated_read_topic_no_duplicate_claims(self, storage, sample_paper_record):
        """Test that running read-topic twice does not increase claim count."""
        storage.upsert_paper(sample_paper_record)
        storage.insert_topic_paper("intracerebral hemorrhage", "paper1")

        claim = Claim(
            claim_id="c1",
            paper_id="paper1",
            claim_text="ICH has high mortality",
            evidence_type="result",
            topic="intracerebral hemorrhage",
        )

        # First run
        storage.upsert_claim_idempotent(claim)
        count1 = storage.count_claims()

        # Second run (same claim)
        storage.upsert_claim_idempotent(claim)
        count2 = storage.count_claims()

        assert count1 == 1
        assert count2 == 1


class TestMigration:
    def test_old_db_gets_new_columns(self, tmp_path):
        """Test that opening an old DB migrates correctly."""
        db = tmp_path / "old.sqlite"
        # Create old-style DB
        import sqlite3
        conn = sqlite3.connect(str(db))
        conn.executescript("""
            CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT);
            CREATE TABLE claims (claim_id TEXT PRIMARY KEY, paper_id TEXT, claim_text TEXT, evidence_type TEXT, confidence REAL, source_location TEXT, topic TEXT, created_at TEXT);
            CREATE TABLE topic_papers (topic TEXT, paper_id TEXT, source TEXT, relevance_score REAL, created_at TEXT, PRIMARY KEY(topic, paper_id));
        """)
        conn.close()

        # Open with new Storage - should migrate
        s = Storage(db_path=db)
        # Verify new columns exist by inserting a claim with new fields
        claim = Claim(
            claim_id="test1",
            paper_id="p1",
            claim_text="test claim",
            evidence_type="result",
            topic="test",
        )
        s.upsert_claim_idempotent(claim, extraction_method="claw")
        claims = s.get_claims_for_paper("p1")
        assert claims[0]["extraction_method"] == "claw"
        s.close()
