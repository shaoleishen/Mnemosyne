"""Pi RPC agent provider for batch and long-running tasks."""

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
    """Extract JSON from Pi RPC output."""
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start == -1:
        raise AgentSchemaError("No JSON object found in Pi RPC output")

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

    raise AgentSchemaError("No complete JSON object found in Pi RPC output")


class PiRpcProvider:
    """Pi RPC agent provider for batch and long-running tasks."""

    name = "pi-rpc"

    def __init__(
        self,
        pi_bin: str = "pi",
        rpc_endpoint: str = "",
        model: str = "",
        timeout_seconds: int = 600,
        max_retries: int = 2,
    ) -> None:
        self.pi_bin = pi_bin
        self.rpc_endpoint = rpc_endpoint
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def capabilities(self) -> set[str]:
        return {"structured_json", "rpc", "batch", "local_harness"}

    def is_available(self) -> bool:
        from pathlib import Path
        return Path(self.pi_bin).exists() and bool(self.rpc_endpoint)

    def _build_command(self) -> list[str]:
        cmd = [self.pi_bin, "--mode", "rpc"]
        if self.model:
            cmd.extend(["--model", self.model])
        return cmd

    def run(self, task: AgentTask) -> AgentResult:
        """Execute a task via Pi RPC mode."""
        prompt = build_prompt_for_task(task)
        last_error: Exception | None = None

        # Build RPC payload
        rpc_payload = {
            "method": "chat",
            "params": {
                "prompt": prompt,
                "timeout": task.timeout_seconds,
            },
        }

        for attempt in range(self.max_retries + 1):
            try:
                cmd = self._build_command()
                result = subprocess.run(
                    cmd,
                    input=json.dumps(rpc_payload),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                )

                if result.returncode != 0:
                    error_msg = result.stderr.strip() or f"Pi RPC exited with code {result.returncode}"
                    raise AgentProviderError(f"Pi RPC failed: {error_msg}")

                output = result.stdout.strip()
                if not output:
                    raise AgentProviderError("Pi RPC returned empty output")

                parsed = _extract_json(output)
                return AgentResult(
                    task_id=task.task_id,
                    provider=self.name,
                    provider_mode="pi_rpc",
                    model=self.model,
                    status="ok",
                    output_json=parsed,
                    raw_output=output,
                )

            except subprocess.TimeoutExpired:
                last_error = AgentProviderError(f"Pi RPC timed out after {self.timeout_seconds}s")
            except (AgentProviderError, AgentSchemaError) as e:
                last_error = e

            if attempt < self.max_retries:
                time.sleep(2 ** attempt)

        return AgentResult(
            task_id=task.task_id,
            provider=self.name,
            provider_mode="pi_rpc",
            model=self.model,
            status="error",
            error=str(last_error),
        )
