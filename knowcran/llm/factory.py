"""Factory for creating LLM providers based on configuration."""

from __future__ import annotations

from typing import Any

from knowcran.config import Settings


def create_provider(settings: Settings) -> Any:
    """Create an LLM provider based on the current settings.

    Returns:
        An LLM provider instance, or None if provider is 'none'.
    """
    if settings.llm_provider == "none":
        return None
    if settings.llm_provider == "claw":
        from knowcran.llm.claw_provider import ClawLLMProvider

        if not settings.claw_bin:
            from knowcran.llm.base import LLMProviderError

            raise LLMProviderError(
                "Claw provider selected but no Claw binary found. "
                "Set MNEMOSYNE_CLAW_BIN or ensure claw is on PATH."
            )
        return ClawLLMProvider(
            claw_bin=settings.claw_bin,
            model=settings.claw_model,
            permission_mode=settings.claw_permission_mode,
            timeout_seconds=settings.claw_timeout_seconds,
            max_retries=settings.claw_max_retries,
        )
    from knowcran.llm.base import LLMProviderError

    raise LLMProviderError(f"Unknown LLM provider: {settings.llm_provider}")
