"""Generator node for the RAG flow.

Calls the OpenAI-compatible vision/chat provider to generate answers.
"""

from __future__ import annotations

import logging
from typing import Any

from knowcran.rag.state import AgentState
from knowcran.rag.prompts import format_multimodal_prompt, format_text_only_prompt

logger = logging.getLogger(__name__)


def generate_answer(
    state: AgentState,
    vision_router: Any | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Generate an answer using the OpenAI-compatible provider.

    This node:
    1. Checks if media context is present
    2. Formats appropriate prompt (multimodal or text-only)
    3. Calls the chat/completions API
    4. Returns the generated response

    Args:
        state: Current RAG agent state
        vision_router: OpenAI-compatible provider router
        api_base: Legacy direct API base URL
        api_key: Legacy direct API key
        model: Legacy direct model name

    Returns:
        Updated state with final_response
    """
    context_texts = state.get("context_texts", [])
    context_media = state.get("context_media", [])
    auxiliary_context = state.get("auxiliary_context", [])
    query = state["query"]

    # Determine if multimodal generation is needed
    has_media = len(context_media) > 0

    # Format prompt based on available context
    if has_media:
        messages = format_multimodal_prompt(
            query=query,
            context_texts=context_texts,
            context_media=context_media,
            auxiliary_context=auxiliary_context,
        )
    else:
        messages = format_text_only_prompt(
            query=query,
            context_texts=context_texts,
        )

    # Call the API via the shared vision router when available.
    if vision_router is not None:
        result = vision_router.chat(messages=messages, max_tokens=4096)
        if result.get("status") == "success":
            return {"final_response": result.get("content", "")}
        error = result.get("error", "No healthy vision providers configured")
        logger.error(f"Generation failed through vision router: {error}")
        return {
            "final_response": f"Error generating response: {error}",
            "degraded_reason": error,
        }

    if not (api_base and api_key and model):
        error = "No OpenAI-compatible vision/chat provider configured for RAG generation."
        logger.error(error)
        return {
            "final_response": f"Error generating response: {error}",
            "degraded_reason": error,
        }

    # Legacy direct API call path for explicit configs.
    try:
        response = _call_chat_api(
            messages=messages,
            api_base=api_base,
            api_key=api_key,
            model=model,
        )
        return {"final_response": response}
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        return {
            "final_response": f"Error generating response: {e}",
            "degraded_reason": str(e),
        }


def _call_chat_api(
    messages: list[dict],
    api_base: str,
    api_key: str,
    model: str,
    max_tokens: int = 4096,
) -> str:
    """Call the OpenAI-compatible chat/completions API.

    Args:
        messages: Chat messages
        api_base: API base URL
        api_key: API key
        model: Model name
        max_tokens: Maximum tokens to generate

    Returns:
        Generated text response
    """
    url = f"{api_base.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }

    import httpx

    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            raise Exception(
                f"API returned status {response.status_code}: {response.text}"
            )

        result = response.json()
        choices = result.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")

    return ""
