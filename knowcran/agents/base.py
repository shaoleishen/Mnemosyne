"""Base agent provider protocol and exceptions."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from knowcran.agents.schemas import AgentResult, AgentTask


class AgentProviderError(Exception):
    """Raised when an agent provider call fails."""


class AgentSchemaError(Exception):
    """Raised when agent output fails schema validation."""


@runtime_checkable
class AgentProvider(Protocol):
    """Protocol for agent providers used by KnowCran.

    All implementations must be synchronous and return AgentResult.
    """

    name: str

    def run(self, task: AgentTask) -> AgentResult:
        """Execute an agent task and return the result.

        Args:
            task: The agent task to execute.

        Returns:
            AgentResult with status, output, and metadata.
        """
        ...

    def capabilities(self) -> set[str]:
        """Return the set of capabilities this provider supports.

        Common capabilities:
            structured_json: can return structured JSON
            json_schema: can follow JSON schema constraints
            rpc: supports RPC mode
            sdk: supports SDK mode
            subprocess: uses subprocess invocation
            batch: supports batch tasks
            long_context: supports long context windows
            tool_calls: supports tool/function calls
            local_harness: runs locally as a harness
        """
        ...

    def is_available(self) -> bool:
        """Check if the provider is configured and ready to use."""
        ...
