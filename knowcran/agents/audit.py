"""Agent run audit logging."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from knowcran.agents.schemas import AgentResult, AgentTask
from knowcran.storage import Storage


def audit_agent_run(
    task: AgentTask,
    result: AgentResult,
    storage: Storage,
) -> None:
    """Log an agent run to the agent_runs audit table."""
    input_hash = hashlib.sha256(
        json.dumps(task.input_json, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]

    storage.insert_agent_run(
        run_id=result.task_id,
        provider=result.provider,
        provider_mode=result.provider_mode,
        model=result.model,
        task_type=task.task_type,
        task_id=task.task_id,
        input_hash=input_hash,
        input_json=json.dumps(task.input_json, default=str),
        output_schema_name=task.output_schema_name,
        raw_output=result.raw_output,
        parsed_output_json=json.dumps(result.output_json, default=str) if result.output_json else None,
        status=result.status,
        error=result.error,
        usage_json=json.dumps(result.usage_json, default=str) if result.usage_json else None,
    )
