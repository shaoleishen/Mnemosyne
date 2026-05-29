"""Claw subprocess LLM provider for KnowCran."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from typing import Any

from knowcran.llm.base import LLMProviderError, LLMValidationError

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first valid JSON object from LLM output text.

    Tries direct parse first, then finds the first { ... } block.
    """
    text = text.strip()
    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Find first { ... } block with brace matching
    start = text.find("{")
    if start == -1:
        raise LLMValidationError("No JSON object found in LLM output")

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
                    raise LLMValidationError(f"Found JSON-like block but failed to parse: {candidate[:200]}")
                break

    raise LLMValidationError("No complete JSON object found in LLM output")


class ClawLLMProvider:
    """LLM provider that calls Claw via subprocess."""

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

    def is_available(self) -> bool:
        """Check if Claw binary exists."""
        from pathlib import Path

        return Path(self.claw_bin).exists()

    def _build_command(self, prompt: str) -> list[str]:
        """Build the Claw subprocess command."""
        return [
            self.claw_bin,
            "--model", self.model,
            "--permission-mode", self.permission_mode,
            "--output-format", "json",
            "prompt", prompt,
        ]

    def call(self, prompt: str, task_type: str = "general") -> dict[str, Any]:
        """Call Claw via subprocess and return parsed JSON.

        Args:
            prompt: The prompt to send to Claw.
            task_type: Label for logging (e.g. "extraction", "rerank").

        Returns:
            Parsed JSON dict from Claw's output.

        Raises:
            LLMProviderError: If Claw fails after retries.
            LLMValidationError: If output cannot be parsed as JSON.
        """
        cmd = self._build_command(prompt)
        last_error: Exception | None = None
        
        # Prepare environment with Mimo API variables
        env = os.environ.copy()
        mimo_env_vars = [
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_MODEL",
            "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "ANTHROPIC_DEFAULT_OPUS_MODEL",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        ]
        for var in mimo_env_vars:
            value = os.getenv(var)
            if value:
                env[var] = value

        for attempt in range(self.max_retries + 1):
            try:
                logger.debug("Claw call attempt %d/%d for task=%s", attempt + 1, self.max_retries + 1, task_type)
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    env=env,
                )

                if result.returncode != 0:
                    error_msg = result.stderr.strip() or f"Claw exited with code {result.returncode}"
                    raise LLMProviderError(f"Claw subprocess failed: {error_msg}")

                output = result.stdout.strip()
                if not output:
                    raise LLMProviderError("Claw returned empty output")

                return _extract_json(output)

            except subprocess.TimeoutExpired:
                last_error = LLMProviderError(f"Claw timed out after {self.timeout_seconds}s")
                logger.warning("Claw timeout on attempt %d", attempt + 1)
            except (LLMProviderError, LLMValidationError) as e:
                last_error = e
                logger.warning("Claw error on attempt %d: %s", attempt + 1, e)

            if attempt < self.max_retries:
                wait = 2 ** attempt
                logger.info("Retrying in %ds...", wait)
                time.sleep(wait)

        raise last_error or LLMProviderError("Claw call failed after all retries")
