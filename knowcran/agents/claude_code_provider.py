"""Claude Code agent provider - optional subprocess integration."""

from __future__ import annotations

import json
import logging
import subprocess
import time
from typing import Any

from knowcran.agents.base import AgentProviderError, AgentSchemaError
from knowcran.agents.prompts import build_prompt_for_task
from knowcran.agents.schemas import AgentResult, AgentTask

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from Claude Code output."""
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start == -1:
        raise AgentSchemaError("No JSON object found in Claude Code output")

    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    result = json.loads(candidate)
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    raise AgentSchemaError(f"Failed to parse JSON: {candidate[:200]}")
                break

    raise AgentSchemaError("No complete JSON object found in Claude Code output")


class ClaudeCodeProvider:
    """Claude Code subprocess agent provider."""

    name = "claude-code"

    def __init__(
        self,
        claude_bin: str = "claude",
        timeout_seconds: int = 600,
        max_retries: int = 2,
    ) -> None:
        self.claude_bin = claude_bin
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def capabilities(self) -> set[str]:
        return {"structured_json", "subprocess"}

    def is_available(self) -> bool:
        from pathlib import Path
        return Path(self.claude_bin).exists()

    def run(self, task: AgentTask) -> AgentResult:
        """Execute a task via Claude Code subprocess with idle timeout."""
        from knowcran.agents.subprocess_runner import run_with_idle_timeout

        prompt = build_prompt_for_task(task)
        task_timeout = task.timeout_seconds or self.timeout_seconds
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                cmd = [self.claude_bin, "-p", "--output-format", "json", prompt]
                result = run_with_idle_timeout(
                    cmd,
                    idle_timeout_seconds=task_timeout,
                )

                if result.idle_timed_out:
                    last_error = AgentProviderError(f"Claude Code idle timeout after {task_timeout}s")
                    if attempt < self.max_retries:
                        time.sleep(2 ** attempt)
                    continue

                if result.timed_out:
                    last_error = AgentProviderError(f"Claude Code hard timeout")
                    if attempt < self.max_retries:
                        time.sleep(2 ** attempt)
                    continue

                if result.returncode != 0:
                    error_msg = result.stderr.strip() or f"Claude Code exited with code {result.returncode}"
                    raise AgentProviderError(f"Claude Code failed: {error_msg}")

                output = result.stdout.strip()
                if not output:
                    raise AgentProviderError("Claude Code returned empty output")

                parsed = _extract_json(output)
                return AgentResult(
                    task_id=task.task_id,
                    provider=self.name,
                    provider_mode="claude_code",
                    status="ok",
                    output_json=parsed,
                    raw_output=output,
                )

            except (AgentProviderError, AgentSchemaError) as e:
                last_error = e

            if attempt < self.max_retries:
                time.sleep(2 ** attempt)

        return AgentResult(
            task_id=task.task_id,
            provider=self.name,
            provider_mode="claude_code",
            status="error",
            error=str(last_error),
        )
