"""Tests for reading workflow: claim extraction, idempotency, biomedical awareness."""

from __future__ import annotations

from pathlib import Path

from knowcran.models import PaperRecord
from knowcran.reading import read_topic
from knowcran.storage import Storage


def _seed_papers(storage: Storage, topic: str, count: int = 3) -> None:
    for i in range(count):
        paper = PaperRecord(
            paper_id=f"p{i}",
            title=f"Paper {i} about {topic.title()}",
            abstract=f"This study demonstrates significant findings in {topic}. We used a cohort study with patients. Results show increased levels. However, small sample size is a limitation.",
            year=2020 + i,
            venue="Test Journal",
            doi=f"10.1000/test{i}",
            discovered_by="keyword_search",
        )
        storage.upsert_paper(paper)


def test_read_topic_idempotent(tmp_path: Path) -> None:
    """Re-running read_topic must not duplicate claims."""
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)
    _seed_papers(storage, "celiac disease")

    # First run
    claims1 = read_topic("celiac disease", limit=10, storage=storage)
    count1 = storage.count_claims()
    assert count1 > 0

    # Second run - must not duplicate
    claims2 = read_topic("celiac disease", limit=10, storage=storage)
    count2 = storage.count_claims()

    assert count2 == count1, f"Claims duplicated: {count1} -> {count2}"
    assert len(claims2) == len(claims1)

    storage.close()


def test_deterministic_claim_ids(tmp_path: Path) -> None:
    """Same paper + topic must produce same claim IDs."""
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)
    _seed_papers(storage, "celiac disease", count=1)

    claims1 = read_topic("celiac disease", limit=1, storage=storage)
    claims2 = read_topic("celiac disease", limit=1, storage=storage)

    ids1 = {c.claim_id for c in claims1}
    ids2 = {c.claim_id for c in claims2}

    assert ids1 == ids2, "Claim IDs should be deterministic across runs"

    storage.close()


def test_read_topic_extracts_claims(tmp_path: Path) -> None:
    """read_topic must extract claims from matching papers."""
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)
    _seed_papers(storage, "celiac disease")

    claims = read_topic("celiac disease", limit=10, storage=storage)

    assert len(claims) > 0
    evidence_types = {c.evidence_type for c in claims}
    assert "abstract_summary" in evidence_types
    assert "result" in evidence_types

    storage.close()


def test_structured_abstract_labels_cleaned(tmp_path: Path) -> None:
    """Structured abstract labels should not appear in claim text."""
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)

    paper = PaperRecord(
        paper_id="p-structured",
        title="Paper about Celiac Disease",
        abstract="BACKGROUND: Celiac disease is common. METHODS: We studied 100 patients. RESULTS: Significant improvement was observed. CONCLUSION: Treatment is effective.",
        year=2023,
        venue="Test Journal",
        discovered_by="keyword_search",
    )
    storage.upsert_paper(paper)

    claims = read_topic("celiac disease", limit=1, storage=storage)

    for c in claims:
        assert "BACKGROUND" not in c.claim_text
        assert "METHODS" not in c.claim_text
        assert "RESULTS" not in c.claim_text
        assert "CONCLUSION" not in c.claim_text

    storage.close()


def test_animal_model_open_question(tmp_path: Path) -> None:
    """Animal/model papers should get translation question instead of population question."""
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)

    paper = PaperRecord(
        paper_id="p-animal",
        title="ICH in Rat Model",
        abstract="We used a collagenase-induced intracerebral hemorrhage model in rats. Results show significant neuronal damage.",
        year=2023,
        venue="Test Journal",
        discovered_by="keyword_search",
    )
    storage.upsert_paper(paper)

    claims = read_topic("intracerebral hemorrhage", limit=1, storage=storage)

    open_q_claims = [c for c in claims if c.evidence_type == "open_question"]
    assert len(open_q_claims) == 1
    assert "translat" in open_q_claims[0].claim_text.lower() or \
           "animal" in open_q_claims[0].claim_text.lower() or \
           "model" in open_q_claims[0].claim_text.lower()

    storage.close()


def test_human_study_population_question(tmp_path: Path) -> None:
    """Human studies without population info should get population question."""
    db_path = tmp_path / "test.sqlite"
    storage = Storage(db_path=db_path)

    paper = PaperRecord(
        paper_id="p-human",
        title="Intracerebral Hemorrhage Treatment Study",
        abstract="This is a brief abstract about treatment.",
        year=2023,
        venue="Test Journal",
        discovered_by="keyword_search",
    )
    storage.upsert_paper(paper)

    claims = read_topic("intracerebral hemorrhage", limit=1, storage=storage)

    open_q_claims = [c for c in claims if c.evidence_type == "open_question"]
    assert len(open_q_claims) == 1
    assert "population" in open_q_claims[0].claim_text.lower() or "cohort" in open_q_claims[0].claim_text.lower()

    storage.close()
