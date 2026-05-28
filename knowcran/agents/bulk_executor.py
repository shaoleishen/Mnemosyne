"""Bulk agent execution with chunking, timeout budgets, and fallback."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console

from knowcran.agents.base import AgentProvider
from knowcran.agents.schemas import AgentResult, AgentTask

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class ChunkConfig:
    """Configuration for chunked execution."""
    rerank_chunk_size: int = 15
    extraction_chunk_size: int = 1
    review_chunk_size: int = 1
    health_check_timeout: int = 20
    extraction_timeout: int = 60
    rerank_timeout: int = 90
    review_timeout: int = 180
    max_retries: int = 2
    max_timeouts: int = 3
    fallback_provider: str | None = "deterministic"


@dataclass
class ChunkResult:
    """Result of a single chunk execution."""
    chunk_id: str
    task_type: str
    input_count: int
    status: str  # completed, timeout, schema_error, provider_error, fallback_used
    provider: str
    fallback_from: str | None = None
    duration_ms: int = 0
    retry_count: int = 0
    output: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class WorkflowSummary:
    """Summary of a bulk workflow execution."""
    workflow_id: str
    task_type: str
    topic: str
    total_chunks: int = 0
    succeeded: int = 0
    retried: int = 0
    timed_out: int = 0
    fell_back: int = 0
    skipped_cache: int = 0
    avg_latency_ms: float = 0.0
    chunks: list[ChunkResult] = field(default_factory=list)


class BulkExecutor:
    """Executes agent tasks in chunks with timeout budgets and fallback."""

    def __init__(
        self,
        provider: AgentProvider,
        config: ChunkConfig | None = None,
        fallback_provider: AgentProvider | None = None,
        storage: Any = None,
    ) -> None:
        self.provider = provider
        self.config = config or ChunkConfig()
        self.fallback_provider = fallback_provider
        self.storage = storage

    def _get_chunk_size(self, task_type: str) -> int:
        sizes = {
            "relevance_rerank": self.config.rerank_chunk_size,
            "claim_extraction": self.config.extraction_chunk_size,
            "review_synthesis": self.config.review_chunk_size,
        }
        return sizes.get(task_type, 1)

    def _get_timeout(self, task_type: str) -> int:
        timeouts = {
            "health_check": self.config.health_check_timeout,
            "claim_extraction": self.config.extraction_timeout,
            "relevance_rerank": self.config.rerank_timeout,
            "review_synthesis": self.config.review_timeout,
        }
        return timeouts.get(task_type, self.config.extraction_timeout)

    def execute_rerank(
        self,
        topic: str,
        papers: list[dict[str, Any]],
        storage: Any = None,
    ) -> tuple[list[dict[str, Any]], WorkflowSummary]:
        """Execute reranking in chunks.

        Returns (updated_papers, summary).
        """
        from knowcran.agents.audit import audit_agent_run

        summary = WorkflowSummary(
            workflow_id=f"rerank-{uuid.uuid4().hex[:8]}",
            task_type="relevance_rerank",
            topic=topic,
        )

        chunk_size = self._get_chunk_size("relevance_rerank")
        timeout = self._get_timeout("relevance_rerank")
        all_decisions: list[dict[str, Any]] = []
        timeout_count = 0

        # Split papers into chunks
        chunks = [papers[i:i + chunk_size] for i in range(0, len(papers), chunk_size)]
        summary.total_chunks = len(chunks)

        for chunk_idx, chunk in enumerate(chunks):
            chunk_id = f"{summary.workflow_id}-c{chunk_idx}"
            console.print(f"  Reranking chunk {chunk_idx + 1}/{len(chunks)} ({len(chunk)} papers)")

            task = AgentTask(
                task_id=chunk_id,
                task_type="relevance_rerank",
                topic=topic,
                input_json={"topic": topic, "papers": chunk},
                output_schema_name="PaperRerankOutput",
                timeout_seconds=timeout,
            )

            result = self._execute_with_retry(task, timeout)
            summary.chunks.append(result)

            if result.status == "completed":
                summary.succeeded += 1
                if result.output:
                    decisions = result.output.get("decisions", [])
                    all_decisions.extend(decisions)
            elif result.status == "timeout":
                summary.timed_out += 1
                timeout_count += 1
                if timeout_count >= self.config.max_timeouts:
                    console.print(f"  [yellow]Max timeouts ({self.config.max_timeouts}) reached, stopping.[/yellow]")
                    break
            elif result.status == "fallback_used":
                summary.fell_back += 1
                if result.output:
                    decisions = result.output.get("decisions", [])
                    all_decisions.extend(decisions)
            else:
                summary.retried += result.retry_count

        # Apply decisions to papers
        score_map: dict[str, float] = {}
        for d in all_decisions:
            if d.get("is_relevant", True):
                score_map[d["paper_id"]] = d.get("score", 0.5)

        for p in papers:
            pid = p.paper_id if hasattr(p, "paper_id") else p.get("paper_id", "")
            if pid in score_map:
                old_score = p.relevance_score if hasattr(p, "relevance_score") else p.get("relevance_score", 0.5)
                new_score = round((old_score + score_map[pid]) / 2, 4)
                if hasattr(p, "relevance_score"):
                    p.relevance_score = new_score
                else:
                    p["relevance_score"] = new_score

        # Calculate average latency
        latencies = [c.duration_ms for c in summary.chunks if c.duration_ms > 0]
        summary.avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0

        return papers, summary

    def execute_extraction(
        self,
        topic: str,
        papers: list[dict[str, Any]],
        storage: Any = None,
    ) -> tuple[list[dict[str, Any]], WorkflowSummary]:
        """Execute claim extraction in chunks.

        Returns (all_claims_dicts, summary).
        """
        summary = WorkflowSummary(
            workflow_id=f"extract-{uuid.uuid4().hex[:8]}",
            task_type="claim_extraction",
            topic=topic,
        )

        timeout = self._get_timeout("claim_extraction")
        all_claims: list[dict[str, Any]] = []
        timeout_count = 0

        summary.total_chunks = len(papers)

        for paper_idx, paper in enumerate(papers):
            chunk_id = f"{summary.workflow_id}-p{paper_idx}"
            if (paper_idx + 1) % 10 == 0 or paper_idx == 0:
                console.print(f"  Extracting claims {paper_idx + 1}/{len(papers)}")

            task = AgentTask(
                task_id=chunk_id,
                task_type="claim_extraction",
                topic=topic,
                paper_id=paper.get("paper_id"),
                input_json={"topic": topic, "paper": paper, "source_text": paper.get("abstract")},
                output_schema_name="PaperExtractionOutput",
                timeout_seconds=timeout,
            )

            result = self._execute_with_retry(task, timeout)
            summary.chunks.append(result)

            if result.status == "completed":
                summary.succeeded += 1
                if result.output:
                    items = result.output.get("evidence_items", [])
                    for item in items:
                        item["_paper_id"] = paper.get("paper_id")
                        item["_provider"] = result.provider
                    all_claims.extend(items)
            elif result.status == "timeout":
                summary.timed_out += 1
                timeout_count += 1
                if timeout_count >= self.config.max_timeouts:
                    console.print(f"  [yellow]Max timeouts ({self.config.max_timeouts}) reached, stopping.[/yellow]")
                    break
            elif result.status == "fallback_used":
                summary.fell_back += 1
                if result.output:
                    items = result.output.get("evidence_items", [])
                    for item in items:
                        item["_paper_id"] = paper.get("paper_id")
                        item["_provider"] = "deterministic"
                    all_claims.extend(items)

        latencies = [c.duration_ms for c in summary.chunks if c.duration_ms > 0]
        summary.avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0

        return all_claims, summary

    def _execute_with_retry(self, task: AgentTask, timeout: int) -> ChunkResult:
        """Execute a single task with retry and fallback."""
        start_time = time.time()
        retry_count = 0
        last_error: str | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                result = self.provider.run(task)

                if result.status == "ok":
                    duration_ms = int((time.time() - start_time) * 1000)
                    return ChunkResult(
                        chunk_id=task.task_id,
                        task_type=task.task_type,
                        input_count=len(task.input_json.get("papers", [])) or 1,
                        status="completed",
                        provider=result.provider,
                        duration_ms=duration_ms,
                        retry_count=retry_count,
                        output=result.output_json,
                    )
                elif result.status == "timeout":
                    last_error = result.error or "timeout"
                    retry_count += 1
                    if attempt < self.config.max_retries:
                        time.sleep(2 ** attempt)
                    continue
                else:
                    last_error = result.error or "provider_error"
                    retry_count += 1
                    if attempt < self.config.max_retries:
                        time.sleep(2 ** attempt)
                    continue

            except Exception as e:
                last_error = str(e)
                retry_count += 1
                if attempt < self.config.max_retries:
                    time.sleep(2 ** attempt)

        # All retries exhausted, try fallback
        if self.fallback_provider:
            try:
                fallback_result = self.fallback_provider.run(task)
                duration_ms = int((time.time() - start_time) * 1000)
                return ChunkResult(
                    chunk_id=task.task_id,
                    task_type=task.task_type,
                    input_count=len(task.input_json.get("papers", [])) or 1,
                    status="fallback_used",
                    provider=fallback_result.provider,
                    fallback_from=self.provider.name,
                    duration_ms=duration_ms,
                    retry_count=retry_count,
                    output=fallback_result.output_json,
                )
            except Exception:
                pass

        duration_ms = int((time.time() - start_time) * 1000)
        return ChunkResult(
            chunk_id=task.task_id,
            task_type=task.task_type,
            input_count=len(task.input_json.get("papers", [])) or 1,
            status="timeout" if "timeout" in (last_error or "").lower() else "provider_error",
            provider=self.provider.name,
            duration_ms=duration_ms,
            retry_count=retry_count,
            error=last_error,
        )


def format_workflow_summary(summary: WorkflowSummary) -> str:
    """Format a workflow summary for CLI output."""
    lines = [
        f"Workflow: {summary.workflow_id}",
        f"Task: {summary.task_type}",
        f"Topic: {summary.topic}",
        f"Chunks: {summary.total_chunks}",
        f"Succeeded: {summary.succeeded}",
        f"Retried: {summary.retried}",
        f"Timed out: {summary.timed_out}",
        f"Fell back: {summary.fell_back}",
        f"Avg latency: {summary.avg_latency_ms:.0f}ms",
    ]

    if summary.chunks:
        providers = set(c.provider for c in summary.chunks)
        lines.append(f"Providers used: {', '.join(providers)}")

        fallback_from = set(c.fallback_from for c in summary.chunks if c.fallback_from)
        if fallback_from:
            lines.append(f"Fallback from: {', '.join(fallback_from)}")

    return "\n".join(lines)
