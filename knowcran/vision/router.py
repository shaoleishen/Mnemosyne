"""Vision API provider router with failure-triggered health routing.

This module provides:
- Provider health management
- Automatic fallback on provider failure
- No constant background polling (health refresh on failure only)
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from knowcran.vision.provider import VisionProvider

logger = logging.getLogger(__name__)

# Default health state file location
_DEFAULT_HEALTH_FILE = "data/runtime/vision_provider_health.json"


class VisionRouter:
    """Router for Vision API providers with health-based fallback.

    Features:
        - Maintains ordered list of providers
        - Routes to first healthy provider
        - On failure, marks provider unhealthy and retries with next
        - Optionally persists health state to disk
        - No background polling - health refreshes on failure only

    Configuration:
        providers: List of VisionProvider instances
        health_file: Path to persist health state (optional)
    """

    def __init__(
        self,
        providers: list[VisionProvider],
        health_file: str | Path | None = None,
    ):
        self.providers = providers
        self.health_file = Path(health_file) if health_file else None

        # Load persisted health state if available
        if self.health_file and self.health_file.exists():
            self._load_health_state()

    def get_healthy_provider(self) -> VisionProvider | None:
        """Get the first healthy provider.

        Returns:
            VisionProvider instance or None if all providers are unhealthy
        """
        for provider in self.providers:
            if provider.is_healthy:
                return provider
        return None

    def describe_media(
        self,
        image_path: str,
        task_type: str = "describe_media",
        prompt: str | None = None,
    ) -> dict[str, Any]:
        """Describe media using the first available healthy provider.

        On failure:
        1. Marks the failed provider as unhealthy
        2. Retries with the next healthy provider
        3. Returns the first successful result

        Args:
            image_path: Path to the image file
            task_type: Type of task ("describe_media" or "table_to_markdown")
            prompt: Custom prompt (optional)

        Returns:
            Dict with description, provider info, and status
        """
        last_error = None

        for provider in self.providers:
            if not provider.is_healthy:
                continue

            try:
                result = provider.describe_media(
                    image_path=image_path,
                    task_type=task_type,
                    prompt=prompt,
                )

                if result.get("status") == "success":
                    # Save health state on success
                    self._save_health_state()
                    return result
                else:
                    # Provider returned error
                    last_error = result.get("error", "Unknown error")
                    provider.mark_unhealthy()
                    logger.warning(
                        f"Vision provider {provider.name} failed: {last_error}"
                    )

            except Exception as e:
                last_error = str(e)
                provider.mark_unhealthy()
                logger.warning(
                    f"Vision provider {provider.name} exception: {e}"
                )

        # All providers failed
        self._save_health_state()
        return {
            "description": "",
            "provider": "none",
            "model": "none",
            "status": "error",
            "error": f"All vision providers failed. Last error: {last_error}",
            "source_type": "auxiliary_interpretation",
        }

    def chat(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Generate chat output using the first healthy provider.

        Health refresh is failure-triggered: a failed provider is marked
        unhealthy and the request is retried on the next configured provider.
        """
        last_error = None

        for provider in self.providers:
            if not provider.is_healthy:
                continue

            try:
                result = provider.chat(messages=messages, max_tokens=max_tokens)

                if result.get("status") == "success":
                    self._save_health_state()
                    return result

                last_error = result.get("error", "Unknown error")
                provider.mark_unhealthy()
                logger.warning(
                    f"Vision provider {provider.name} chat failed: {last_error}"
                )
            except Exception as e:
                last_error = str(e)
                provider.mark_unhealthy()
                logger.warning(
                    f"Vision provider {provider.name} chat exception: {e}"
                )

        self._save_health_state()
        return {
            "content": "",
            "provider": "none",
            "model": "none",
            "status": "error",
            "error": f"All vision providers failed. Last error: {last_error}",
        }

    def reset_health(self) -> None:
        """Reset all providers to healthy state."""
        for provider in self.providers:
            provider.mark_healthy()
        self._save_health_state()
        logger.info("All vision providers reset to healthy state")

    def get_status(self) -> list[dict[str, Any]]:
        """Get health status of all providers.

        Returns:
            List of dicts with provider name, health status, and failure count
        """
        return [
            {
                "name": p.name,
                "healthy": p.is_healthy,
                "failures": p._failure_count,
                "last_failure": p._last_failure,
            }
            for p in self.providers
        ]

    def _save_health_state(self) -> None:
        """Persist health state to disk."""
        if not self.health_file:
            return

        try:
            self.health_file.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "providers": [
                    {
                        "name": p.name,
                        "healthy": p.is_healthy,
                        "failure_count": p._failure_count,
                        "last_failure": p._last_failure,
                    }
                    for p in self.providers
                ],
                "updated_at": time.time(),
            }
            with open(self.health_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save health state: {e}")

    def _load_health_state(self) -> None:
        """Load health state from disk."""
        if not self.health_file or not self.health_file.exists():
            return

        try:
            with open(self.health_file) as f:
                state = json.load(f)

            provider_states = {
                p["name"]: p for p in state.get("providers", [])
            }

            for provider in self.providers:
                if provider.name in provider_states:
                    ps = provider_states[provider.name]
                    if not ps.get("healthy", True):
                        provider.mark_unhealthy()
                    provider._failure_count = ps.get("failure_count", 0)
                    provider._last_failure = ps.get("last_failure")

            logger.info("Loaded vision provider health state")
        except Exception as e:
            logger.warning(f"Failed to load health state: {e}")


def create_router_from_config(
    providers_config: list[dict[str, str]],
    health_file: str | Path | None = None,
) -> VisionRouter:
    """Create a VisionRouter from configuration.

    Args:
        providers_config: List of provider configs with keys:
            - name: Provider name
            - api_base: API base URL
            - api_key: API key
            - model: Model name
        health_file: Path to persist health state (optional)

    Returns:
        VisionRouter instance
    """
    providers = []
    for config in providers_config:
        provider = VisionProvider(
            name=config["name"],
            api_base=config["api_base"],
            api_key=config["api_key"],
            model=config["model"],
        )
        providers.append(provider)

    return VisionRouter(providers=providers, health_file=health_file)
