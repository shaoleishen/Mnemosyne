"""Deterministic fallback agent provider."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from knowcran.agents.schemas import AgentResult, AgentTask


class DeterministicProvider:
    """Deterministic fallback provider that produces results without LLM calls.

    Used when no agent provider is available or as a fallback on LLM failure.
    """

    name = "deterministic"

    def capabilities(self) -> set[str]:
        return {"structured_json"}

    def is_available(self) -> bool:
        return True

    def run(self, task: AgentTask) -> AgentResult:
        """Execute a deterministic task.

        For most task types, returns a minimal valid output.
        The actual deterministic logic lives in reading.py, discovery.py, etc.
        This provider is used when the agent framework needs a provider but
        the real work is done by the calling module's deterministic path.
        """
        try:
            if task.task_type == "health_check":
                output = {"status": "ok", "provider": "deterministic"}
            elif task.task_type == "relevance_rerank":
                # Pass through papers with original scores
                papers = task.input_json.get("papers", [])
                decisions = []
                for p in papers:
                    decisions.append({
                        "paper_id": p.get("paper_id", ""),
                        "is_relevant": True,
                        "score": p.get("score", 0.5),
                        "reason": "deterministic passthrough",
                        "topic_match": "partial",
                        "study_type": "other",
                    })
                output = {"decisions": decisions}
            elif task.task_type == "claim_extraction":
                # Return empty - calling code should use deterministic extractor
                output = {
                    "paper_id": task.paper_id or "",
                    "topic": task.topic or "",
                    "study_type": "other",
                    "evidence_items": [],
                }
            elif task.task_type == "review_synthesis":
                # Return empty - calling code should use deterministic review
                output = {
                    "title": f"Review: {task.topic or 'Unknown'}",
                    "background": [],
                    "main_evidence": [],
                    "methods_and_models": [],
                    "limitations": [],
                    "open_questions": [],
                    "warnings": ["Using deterministic fallback"],
                }
            else:
                output = {"status": "unsupported_task_type", "task_type": task.task_type}

            return AgentResult(
                task_id=task.task_id,
                provider=self.name,
                provider_mode="deterministic",
                status="ok",
                output_json=output,
            )
        except Exception as e:
            return AgentResult(
                task_id=task.task_id,
                provider=self.name,
                provider_mode="deterministic",
                status="error",
                error=str(e),
            )
