"""OpenAI-compatible Vision API provider.

Supports multiple providers: Mimo, Kimi, Qwen, DeepSeek, etc.
Uses OpenAI-compatible chat/completions API with vision capabilities.
"""

from __future__ import annotations

import base64
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from knowcran.vision.prompts import get_prompt_for_task

logger = logging.getLogger(__name__)


class VisionProvider:
    """OpenAI-compatible Vision API provider.

    Supports providers that implement the OpenAI chat/completions API
    with vision capabilities (image input).

    Configuration:
        name: Provider name (e.g., "mimo", "kimi", "qwen", "deepseek")
        api_base: API base URL
        api_key: API key
        model: Model name
        timeout: Request timeout in seconds
    """

    def __init__(
        self,
        name: str,
        api_base: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
    ):
        self.name = name
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._healthy = True
        self._last_failure: float | None = None
        self._failure_count = 0

    @property
    def is_healthy(self) -> bool:
        """Check if the provider is healthy."""
        return self._healthy

    def mark_unhealthy(self) -> None:
        """Mark the provider as unhealthy after a failure."""
        self._healthy = False
        self._last_failure = time.time()
        self._failure_count += 1
        logger.warning(f"Vision provider {self.name} marked unhealthy (failures: {self._failure_count})")

    def mark_healthy(self) -> None:
        """Mark the provider as healthy after a successful request."""
        if not self._healthy:
            logger.info(f"Vision provider {self.name} recovered")
        self._healthy = True
        self._failure_count = 0

    def describe_media(
        self,
        image_path: str,
        task_type: str = "describe_media",
        prompt: str | None = None,
    ) -> dict[str, Any]:
        """Describe media using the Vision API.

        Args:
            image_path: Path to the image file
            task_type: Type of task ("describe_media" or "table_to_markdown")
            prompt: Custom prompt (uses default if None)

        Returns:
            Dict with:
                - description: Generated description
                - provider: Provider name
                - model: Model name
                - status: "success" or "error"
                - error: Error message if failed
                - source_type: "auxiliary_interpretation" or "machine_extracted_table"
        """
        image_path = Path(image_path)

        if not image_path.exists():
            return {
                "description": "",
                "provider": self.name,
                "model": self.model,
                "status": "error",
                "error": f"Image file not found: {image_path}",
                "source_type": "auxiliary_interpretation",
            }

        # Get prompt for task
        if prompt is None:
            prompt = get_prompt_for_task(task_type)

        # Encode image as base64 data URL
        try:
            image_data = _encode_image_as_data_url(image_path)
        except Exception as e:
            return {
                "description": "",
                "provider": self.name,
                "model": self.model,
                "status": "error",
                "error": f"Failed to encode image: {e}",
                "source_type": "auxiliary_interpretation",
            }

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data},
                    },
                ],
            }
        ]

        result = self.chat(messages=messages, max_tokens=4096)
        if result.get("status") == "success":
            source_type = (
                "machine_extracted_table" if task_type == "table_to_markdown"
                else "auxiliary_interpretation"
            )

            return {
                "description": result.get("content", ""),
                "provider": self.name,
                "model": self.model,
                "status": "success",
                "error": None,
                "source_type": source_type,
            }

        return {
            "description": "",
            "provider": self.name,
            "model": self.model,
            "status": "error",
            "error": result.get("error", "Unknown error"),
            "source_type": "auxiliary_interpretation",
        }

    def chat(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Call the OpenAI-compatible chat API.

        Returns a structured result instead of raising so routers can fallback
        consistently across answer generation and media extraction.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        try:
            result = self._call_api(payload)
            self.mark_healthy()
            return {
                "content": _extract_content(result),
                "provider": self.name,
                "model": self.model,
                "status": "success",
                "error": None,
            }
        except Exception as e:
            self.mark_unhealthy()
            logger.error(f"Vision API chat call failed for {self.name}: {e}")
            return {
                "content": "",
                "provider": self.name,
                "model": self.model,
                "status": "error",
                "error": str(e),
            }

    def _call_api(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Make an API call to the Vision provider.

        Args:
            payload: Request payload

        Returns:
            API response as dict

        Raises:
            Exception on API errors
        """
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, json=payload, headers=headers)

            if response.status_code != 200:
                raise Exception(
                    f"API returned status {response.status_code}: {response.text}"
                )

            return response.json()


def _encode_image_as_data_url(image_path: Path) -> str:
    """Encode an image file as a base64 data URL.

    Args:
        image_path: Path to the image file

    Returns:
        Data URL string (e.g., "data:image/png;base64,...")
    """
    # Determine MIME type from extension
    suffix = image_path.suffix.lower()
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    mime_type = mime_types.get(suffix, "image/png")

    # Read and encode
    with open(image_path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode("utf-8")

    return f"data:{mime_type};base64,{b64}"


def _extract_content(response: dict[str, Any]) -> str:
    """Extract content from OpenAI-compatible API response.

    Args:
        response: API response dict

    Returns:
        Extracted text content
    """
    try:
        choices = response.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            return message.get("content", "")
    except (KeyError, IndexError) as e:
        logger.warning(f"Failed to extract content from response: {e}")

    return ""
