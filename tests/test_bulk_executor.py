"""Tests for bulk agent executor."""

from __future__ import annotations

import pytest

from knowcran.agents.bulk_executor import BulkExecutor, ChunkConfig, format_workflow_summary
from knowcran.agents.deterministic_provider import DeterministicProvider
from knowcran.agents.schemas import AgentResult, AgentTask


class SlowProvider:
    """A provider that simulates slow/timeout behavior for testing."""

    name = "slow-test"

    def __init__(self, fail_count: int = 0, timeout_count: int = 0):
        self.fail_count = fail_count
        self.timeout_count = timeout_count
        self.call_count = 0

    def capabilities(self):
        return {"structured_json"}

    def is_available(self):
        return True

    def run(self, task: AgentTask) -> AgentResult:
        self.call_count += 1
        if self.call_count <= self.timeout_count:
            return AgentResult(
                task_id=task.task_id,
                provider=self.name,
                provider_mode="deterministic",
                status="timeout",
                error="Simulated timeout",
            )
        if self.call_count <= self.timeout_count + self.fail_count:
            return AgentResult(
                task_id=task.task_id,
                provider=self.name,
                provider_mode="deterministic",
                status="error",
                error="Simulated error",
            )
        # Return deterministic-like result
        return AgentResult(
            task_id=task.task_id,
            provider=self.name,
            provider_mode="deterministic",
            status="ok",
            output_json={"decisions": [{"paper_id": "p1", "is_relevant": True, "score": 0.8}]},
        )


class TestBulkExecutor:
    def test_chunk_rerank(self):
        provider = DeterministicProvider()
        executor = BulkExecutor(provider=provider, config=ChunkConfig(rerank_chunk_size=2))

        papers = [
            {"paper_id": f"p{i}", "title": f"Paper {i}", "abstract": "Test abstract"}
            for i in range(5)
        ]

        papers_result, summary = executor.execute_rerank("test topic", papers)
        assert summary.total_chunks == 3  # 5 papers / 2 per chunk = 3 chunks
        assert summary.succeeded == 3

    def test_chunk_extraction(self):
        provider = DeterministicProvider()
        executor = BulkExecutor(provider=provider)

        papers = [
            {"paper_id": f"p{i}", "title": f"Paper {i}", "abstract": "Test abstract"}
            for i in range(3)
        ]

        claims, summary = executor.execute_extraction("test topic", papers)
        assert summary.total_chunks == 3

    def test_fallback_on_timeout(self):
        slow = SlowProvider(timeout_count=10)  # Always timeout
        det = DeterministicProvider()
        executor = BulkExecutor(
            provider=slow,
            fallback_provider=det,
            config=ChunkConfig(rerank_chunk_size=5, max_retries=0, max_timeouts=10),
        )

        papers = [{"paper_id": "p1", "title": "Paper 1", "abstract": "Test"}]
        papers_result, summary = executor.execute_rerank("test", papers)
        assert summary.fell_back > 0 or summary.timed_out > 0

    def test_format_summary(self):
        from knowcran.agents.bulk_executor import WorkflowSummary
        summary = WorkflowSummary(
            workflow_id="test-123",
            task_type="relevance_rerank",
            topic="ICH",
            total_chunks=5,
            succeeded=4,
            timed_out=1,
        )
        text = format_workflow_summary(summary)
        assert "test-123" in text
        assert "relevance_rerank" in text
        assert "5" in text
