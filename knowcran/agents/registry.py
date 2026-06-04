"""Agent provider registry and factory."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from knowcran.agents.base import AgentProvider, AgentProviderError

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Registry for agent providers."""

    def __init__(self) -> None:
        self._providers: dict[str, AgentProvider] = {}
        self._default_name: str | None = None

    def register(self, provider: AgentProvider, default: bool = False) -> None:
        """Register an agent provider."""
        self._providers[provider.name] = provider
        if default or self._default_name is None:
            self._default_name = provider.name

    def get(self, name: str | None = None) -> AgentProvider:
        """Get a provider by name, or the default if name is None."""
        target = name or self._default_name
        if target is None:
            raise AgentProviderError("No agent providers registered")
        if target not in self._providers:
            raise AgentProviderError(f"Unknown agent provider: {target}")
        return self._providers[target]

    def list_providers(self) -> list[dict[str, Any]]:
        """List all registered providers with their capabilities."""
        result = []
        for name, provider in self._providers.items():
            result.append({
                "name": name,
                "available": provider.is_available(),
                "capabilities": sorted(provider.capabilities()),
                "is_default": name == self._default_name,
            })
        return result

    @property
    def default_name(self) -> str | None:
        return self._default_name


def _detect_pi_bin() -> str | None:
    """Detect Pi binary path."""
    import os
    env = os.getenv("PI_BIN")
    if env and Path(env).exists():
        return env
    found = shutil.which("pi")
    return found


def _detect_claude_code_bin() -> str | None:
    """Detect Claude Code binary path."""
    import os
    env = os.getenv("CLAUDE_CODE_BIN")
    if env and Path(env).exists():
        return env
    found = shutil.which("claude")
    return found


def _detect_claw_bin() -> str | None:
    """Detect Claw binary path."""
    import os
    env = os.getenv("MNEMOSYNE_CLAW_BIN")
    if env and Path(env).exists():
        return env
    for rel in [
        "../claw-code-main/rust/target/debug/claw.exe",
        "../claw-code-main/rust/target/debug/claw",
    ]:
        p = Path(rel)
        if p.exists():
            return str(p.resolve())
    return shutil.which("claw")


def create_registry_from_env() -> AgentRegistry:
    """Create an agent registry populated from environment variables."""
    import os

    registry = AgentRegistry()

    # Always register deterministic provider
    from knowcran.agents.deterministic_provider import DeterministicProvider
    registry.register(DeterministicProvider())

    # Register Pi print/JSON provider if Pi is available
    pi_bin = _detect_pi_bin()
    if pi_bin:
        from knowcran.agents.pi_print_json_provider import PiPrintJsonProvider
        provider = PiPrintJsonProvider(
            pi_bin=pi_bin,
            model=os.getenv("PI_MODEL", ""),
        )
        registry.register(provider)

    # Register Pi RPC provider if configured
    pi_rpc_endpoint = os.getenv("PI_RPC_ENDPOINT")
    if pi_bin and pi_rpc_endpoint:
        from knowcran.agents.pi_rpc_provider import PiRpcProvider
        provider = PiRpcProvider(
            pi_bin=pi_bin,
            rpc_endpoint=pi_rpc_endpoint,
            model=os.getenv("PI_MODEL", ""),
        )
        registry.register(provider)

    # Register Claw provider if available (optional compatibility)
    claw_bin = _detect_claw_bin()
    if claw_bin:
        from knowcran.agents.claw_provider import ClawAgentProvider
        provider = ClawAgentProvider(
            claw_bin=claw_bin,
            model=os.getenv("MNEMOSYNE_CLAW_MODEL", "sonnet"),
        )
        registry.register(provider)

    # Register Claude Code provider if available
    claude_bin = _detect_claude_code_bin()
    if claude_bin:
        from knowcran.agents.claude_code_provider import ClaudeCodeProvider
        provider = ClaudeCodeProvider(
            claude_bin=claude_bin,
        )
        registry.register(provider)

    # Set default from env
    default = os.getenv("MNEMOSYNE_AGENT_PROVIDER")
    if default and default in registry._providers:
        registry._default_name = default
    elif pi_bin:
        registry._default_name = "pi-print-json"

    return registry


# Module-level singleton
_registry: AgentRegistry | None = None


def get_registry() -> AgentRegistry:
    """Get the global agent registry, creating it if needed."""
    global _registry
    if _registry is None:
        _registry = create_registry_from_env()
    return _registry


def reset_registry() -> None:
    """Reset the global registry (for testing)."""
    global _registry
    _registry = None
