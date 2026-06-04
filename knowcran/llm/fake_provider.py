"""Fake LLM provider for testing."""

from __future__ import annotations

from typing import Any


class FakeLLMProvider:
    """A fake LLM provider that returns pre-configured responses for testing."""

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[dict[str, Any]] = []

    def is_available(self) -> bool:
        return True

    def call(self, prompt: str, task_type: str = "general") -> dict[str, Any]:
        """Return a pre-configured response for the given task_type.

        Args:
            prompt: The prompt (recorded but not used for matching).
            task_type: Key into the pre-configured responses dict.

        Returns:
            Pre-configured response dict.

        Raises:
            KeyError: If no response is configured for the task_type.
        """
        self.calls.append({"prompt": prompt, "task_type": task_type})
        if task_type in self.responses:
            return self.responses[task_type]
        # Return a minimal valid response if no specific one configured
        return {"status": "ok", "task_type": task_type}
