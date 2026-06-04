"""Agent task and result schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentTask(BaseModel):
    """A task to be executed by an agent provider."""

    task_id: str
    task_type: Literal[
        "relevance_rerank",
        "claim_extraction",
        "review_synthesis",
        "metadata_repair",
        "health_check",
    ]
    topic: str | None = None
    paper_id: str | None = None
    input_json: dict[str, Any] = Field(default_factory=dict)
    output_schema_name: str = ""
    timeout_seconds: int = 600
    trace: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    """Result from an agent provider execution."""

    task_id: str
    provider: str
    provider_mode: Literal[
        "pi_print_json",
        "pi_rpc",
        "pi_sdk",
        "claude_code",
        "claw",
        "deterministic",
    ]
    model: str | None = None
    status: Literal["ok", "error", "timeout", "schema_error"]
    output_json: dict[str, Any] | None = None
    raw_output: str | None = None
    error: str | None = None
    usage_json: dict[str, Any] = Field(default_factory=dict)
