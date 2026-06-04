"""Tests for agent schemas and registry."""

from __future__ import annotations

import pytest

from knowcran.agents.base import AgentProviderError
from knowcran.agents.deterministic_provider import DeterministicProvider
from knowcran.agents.registry import AgentRegistry
from knowcran.agents.schemas import AgentResult, AgentTask


class TestAgentTask:
    def test_valid_task(self):
        task = AgentTask(
            task_id="t1",
            task_type="relevance_rerank",
            topic="ICH",
            input_json={"papers": []},
            output_schema_name="PaperRerankOutput",
        )
        assert task.task_id == "t1"
        assert task.task_type == "relevance_rerank"

    def test_defaults(self):
        task = AgentTask(task_id="t2", task_type="health_check")
        assert task.timeout_seconds == 600
        assert task.trace == {}

    def test_invalid_task_type_rejected(self):
        with pytest.raises(Exception):
            AgentTask(task_id="t3", task_type="invalid_type")


class TestAgentResult:
    def test_valid_result(self):
        result = AgentResult(
            task_id="t1",
            provider="pi-print-json",
            provider_mode="pi_print_json",
            status="ok",
            output_json={"decisions": []},
        )
        assert result.status == "ok"

    def test_error_result(self):
        result = AgentResult(
            task_id="t2",
            provider="deterministic",
            provider_mode="deterministic",
            status="error",
            error="Something failed",
        )
        assert result.error == "Something failed"

    def test_invalid_status_rejected(self):
        with pytest.raises(Exception):
            AgentResult(
                task_id="t3",
                provider="test",
                provider_mode="deterministic",
                status="invalid",
            )

    def test_invalid_mode_rejected(self):
        with pytest.raises(Exception):
            AgentResult(
                task_id="t4",
                provider="test",
                provider_mode="invalid_mode",
                status="ok",
            )


class TestDeterministicProvider:
    def test_is_available(self):
        p = DeterministicProvider()
        assert p.is_available() is True

    def test_capabilities(self):
        p = DeterministicProvider()
        assert "structured_json" in p.capabilities()

    def test_health_check(self):
        p = DeterministicProvider()
        task = AgentTask(task_id="h1", task_type="health_check")
        result = p.run(task)
        assert result.status == "ok"
        assert result.provider == "deterministic"
        assert result.output_json["status"] == "ok"

    def test_relevance_rerank_passthrough(self):
        p = DeterministicProvider()
        task = AgentTask(
            task_id="r1",
            task_type="relevance_rerank",
            topic="ICH",
            input_json={
                "papers": [
                    {"paper_id": "p1", "score": 0.8},
                    {"paper_id": "p2", "score": 0.6},
                ],
            },
        )
        result = p.run(task)
        assert result.status == "ok"
        assert len(result.output_json["decisions"]) == 2

    def test_claim_extraction_returns_empty(self):
        p = DeterministicProvider()
        task = AgentTask(
            task_id="e1",
            task_type="claim_extraction",
            paper_id="p1",
            topic="ICH",
            input_json={"paper": {"paper_id": "p1"}},
        )
        result = p.run(task)
        assert result.status == "ok"
        assert result.output_json["evidence_items"] == []

    def test_review_synthesis_returns_empty(self):
        p = DeterministicProvider()
        task = AgentTask(
            task_id="s1",
            task_type="review_synthesis",
            topic="ICH",
        )
        result = p.run(task)
        assert result.status == "ok"
        assert "warnings" in result.output_json


class TestAgentRegistry:
    def test_register_and_get(self):
        reg = AgentRegistry()
        p = DeterministicProvider()
        reg.register(p)
        assert reg.get("deterministic") is p

    def test_default_provider(self):
        reg = AgentRegistry()
        p = DeterministicProvider()
        reg.register(p, default=True)
        assert reg.get() is p
        assert reg.default_name == "deterministic"

    def test_unknown_provider_raises(self):
        reg = AgentRegistry()
        with pytest.raises(AgentProviderError, match="Unknown agent provider"):
            reg.get("nonexistent")

    def test_no_providers_raises(self):
        reg = AgentRegistry()
        with pytest.raises(AgentProviderError, match="No agent providers"):
            reg.get()

    def test_list_providers(self):
        reg = AgentRegistry()
        p = DeterministicProvider()
        reg.register(p)
        providers = reg.list_providers()
        assert len(providers) == 1
        assert providers[0]["name"] == "deterministic"
        assert providers[0]["available"] is True
