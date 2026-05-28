"""Claw agent provider - optional compatibility wrapper."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from typing import Any

from knowcran.agents.base import AgentProviderError, AgentSchemaError
from knowcran.agents.schemas import AgentResult, AgentTask

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first valid JSON object from output text."""
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start == -1:
        raise AgentSchemaError("No JSON object found in output")

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
                    raise AgentSchemaError(f"Found JSON-like block but failed to parse: {candidate[:200]}")
                break

    raise AgentSchemaError("No complete JSON object found in output")


class ClawAgentProvider:
    """Claw subprocess agent provider - optional compatibility."""

    name = "claw"

    def __init__(
        self,
        claw_bin: str,
        model: str = "sonnet",
        permission_mode: str = "read-only",
        timeout_seconds: int = 600,
        max_retries: int = 2,
    ) -> None:
        self.claw_bin = claw_bin
        self.model = model
        self.permission_mode = permission_mode
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def capabilities(self) -> set[str]:
        return {"structured_json", "subprocess", "local_harness"}

    def is_available(self) -> bool:
        from pathlib import Path
        return Path(self.claw_bin).exists()

    def _build_command(self, prompt: str) -> list[str]:
        return [
            self.claw_bin,
            "--model", self.model,
            "--permission-mode", self.permission_mode,
            "--output-format", "json",
            "prompt", prompt,
        ]

    def run(self, task: AgentTask) -> AgentResult:
        """Execute a task via Claw subprocess."""
        from knowcran.agents.prompts import build_prompt_for_task
        prompt = build_prompt_for_task(task)
        cmd = self._build_command(prompt)
        last_error: Exception | None = None

        env = os.environ.copy()

        for attempt in range(self.max_retries + 1):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    env=env,
                )

                if result.returncode != 0:
                    error_msg = result.stderr.strip() or f"Claw exited with code {result.returncode}"
                    raise AgentProviderError(f"Claw subprocess failed: {error_msg}")

                output = result.stdout.strip()
                if not output:
                    raise AgentProviderError("Claw returned empty output")

                parsed = _extract_json(output)
                return AgentResult(
                    task_id=task.task_id,
                    provider=self.name,
                    provider_mode="claw",
                    model=self.model,
                    status="ok",
                    output_json=parsed,
                    raw_output=output,
                )

            except subprocess.TimeoutExpired:
                last_error = AgentProviderError(f"Claw timed out after {self.timeout_seconds}s")
            except (AgentProviderError, AgentSchemaError) as e:
                last_error = e

            if attempt < self.max_retries:
                time.sleep(2 ** attempt)

        return AgentResult(
            task_id=task.task_id,
            provider=self.name,
            provider_mode="claw",
            model=self.model,
            status="error",
            error=str(last_error),
        )
