"""Base LLM provider protocol and exceptions."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class LLMProviderError(Exception):
    """Raised when an LLM provider call fails."""


class LLMValidationError(Exception):
    """Raised when LLM output fails schema validation."""


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers used by KnowCran.

    All implementations must be synchronous and return parsed JSON.
    """

    def call(self, prompt: str, task_type: str = "general") -> dict[str, Any]:
        """Send a prompt to the LLM and return parsed JSON output.

        Args:
            prompt: The prompt to send.
            task_type: Label for the task (e.g. "relevance_rerank", "extraction", "review_synthesis").

        Returns:
            Parsed JSON dict from the LLM response.

        Raises:
            LLMProviderError: If the call fails after retries.
            LLMValidationError: If the output cannot be parsed as valid JSON.
        """
        ...

    def is_available(self) -> bool:
        """Check if the provider is configured and ready to use."""
        ...
