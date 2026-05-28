"""Pi print/JSON agent provider."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from knowcran.agents.base import AgentProviderError, AgentSchemaError
from knowcran.agents.prompts import build_prompt_for_task
from knowcran.agents.schemas import AgentResult, AgentTask

logger = logging.getLogger(__name__)

# Max prompt length before using stdin/temp file instead of argv
_MAX_ARGV_PROMPT_LENGTH = 4000


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from Pi output.

    Handles:
    - Direct JSON
    - JSON envelope with message/assistant/content field
    - Markdown fenced JSON
    """
    text = text.strip()

    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return _unwrap_envelope(result)
    except json.JSONDecodeError:
        pass

    # Try stripping markdown fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (fences)
        inner_lines = []
        in_fence = False
        for line in lines:
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                inner_lines.append(line)
        if inner_lines:
            inner = "\n".join(inner_lines).strip()
            try:
                result = json.loads(inner)
                if isinstance(result, dict):
                    return _unwrap_envelope(result)
            except json.JSONDecodeError:
                pass

    # Find first { ... } block with brace matching
    start = text.find("{")
    if start == -1:
        raise AgentSchemaError("No JSON object found in Pi output")

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
                        return _unwrap_envelope(result)
                except json.JSONDecodeError:
                    raise AgentSchemaError(f"Found JSON-like block but failed to parse: {candidate[:200]}")
                break

    raise AgentSchemaError("No complete JSON object found in Pi output")


def _unwrap_envelope(data: dict[str, Any]) -> dict[str, Any]:
    """Unwrap Pi's JSON envelope if present.

    Pi may return:
    - {"message": "..."} where message is JSON string
    - {"assistant": {"content": "..."}} where content is JSON string
    - {"content": "..."} where content is JSON string
    - Direct data dict
    """
    # If it has a 'message' field that's a string, try to parse it
    if "message" in data and isinstance(data["message"], str):
        try:
            inner = json.loads(data["message"])
            if isinstance(inner, dict):
                return inner
        except json.JSONDecodeError:
            pass

    # If it has an 'assistant' field with 'content'
    if "assistant" in data and isinstance(data["assistant"], dict):
        content = data["assistant"].get("content", "")
        if isinstance(content, str):
            try:
                inner = json.loads(content)
                if isinstance(inner, dict):
                    return inner
            except json.JSONDecodeError:
                pass

    # If it has a 'content' field that's a string
    if "content" in data and isinstance(data["content"], str):
        try:
            inner = json.loads(data["content"])
            if isinstance(inner, dict):
                return inner
        except json.JSONDecodeError:
            pass

    return data


class PiPrintJsonProvider:
    """Pi print/JSON agent provider.

    Calls Pi with -p --mode json for structured output.
    """

    name = "pi-print-json"

    def __init__(
        self,
        pi_bin: str = "pi",
        model: str = "",
        timeout_seconds: int = 600,
        max_retries: int = 2,
    ) -> None:
        self.pi_bin = pi_bin
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def capabilities(self) -> set[str]:
        return {"structured_json", "subprocess", "local_harness"}

    def is_available(self) -> bool:
        return Path(self.pi_bin).exists()

    def _build_command(self) -> list[str]:
        """Build the base Pi command (without prompt)."""
        cmd = [self.pi_bin, "-p", "--mode", "json", "--no-session", "--no-tools"]
        if self.model:
            cmd.extend(["--model", self.model])
        return cmd

    def _run_with_prompt(self, prompt: str) -> subprocess.CompletedProcess[str]:
        """Run Pi with prompt, using stdin for long prompts."""
        cmd = self._build_command()

        if len(prompt) > _MAX_ARGV_PROMPT_LENGTH:
            # Use temp file for long prompts
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                f.write(prompt)
                temp_path = f.name
            try:
                # Read from temp file via shell redirect
                result = subprocess.run(
                    f'{cmd[0]} {" ".join(cmd[1:])} < "{temp_path}"',
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                )
                return result
            finally:
                Path(temp_path).unlink(missing_ok=True)
        else:
            cmd.append(prompt)
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )

    def run(self, task: AgentTask) -> AgentResult:
        """Execute a task via Pi print/JSON mode."""
        prompt = build_prompt_for_task(task)
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                result = self._run_with_prompt(prompt)

                if result.returncode != 0:
                    error_msg = result.stderr.strip() or f"Pi exited with code {result.returncode}"
                    raise AgentProviderError(f"Pi subprocess failed: {error_msg}")

                output = result.stdout.strip()
                if not output:
                    raise AgentProviderError("Pi returned empty output")

                parsed = _extract_json(output)
                return AgentResult(
                    task_id=task.task_id,
                    provider=self.name,
                    provider_mode="pi_print_json",
                    model=self.model,
                    status="ok",
                    output_json=parsed,
                    raw_output=output,
                )

            except subprocess.TimeoutExpired:
                last_error = AgentProviderError(f"Pi timed out after {self.timeout_seconds}s")
                logger.warning("Pi timeout on attempt %d", attempt + 1)
            except (AgentProviderError, AgentSchemaError) as e:
                last_error = e
                logger.warning("Pi error on attempt %d: %s", attempt + 1, e)

            if attempt < self.max_retries:
                wait = 2 ** attempt
                logger.info("Retrying in %ds...", wait)
                time.sleep(wait)

        return AgentResult(
            task_id=task.task_id,
            provider=self.name,
            provider_mode="pi_print_json",
            model=self.model,
            status="error",
            error=str(last_error),
        )
