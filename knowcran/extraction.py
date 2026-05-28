"""Evidence extraction from papers, with optional LLM-powered extraction."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from knowcran.llm.base import LLMProviderError, LLMValidationError
from knowcran.llm.prompts import build_extraction_prompt
from knowcran.llm.schemas import PaperExtractionOutput
from knowcran.models import Claim
from knowcran.reading import _extract_claims as deterministic_extract


def extract_paper_claims_with_llm(
    paper: dict[str, Any],
    topic: str,
    provider: Any,
) -> list[Claim]:
    """Extract claims from a paper using LLM-powered extraction.

    Args:
        paper: Paper dict with paper_id, title, abstract.
        topic: Research topic.
        provider: LLM provider instance.

    Returns:
        List of Claim objects extracted by the LLM.

    Raises:
        LLMProviderError: If the LLM call fails.
        LLMValidationError: If the LLM output fails schema validation.
    """
    prompt = build_extraction_prompt(topic, paper)
    result = provider.call(prompt, task_type="extraction")
    parsed = PaperExtractionOutput.model_validate(result)

    claims: list[Claim] = []
    paper_id = paper["paper_id"]

    for item in parsed.evidence_items:
        claim_text = item.claim_text.strip()
        if not claim_text:
            continue

        claim_id = _deterministic_claim_id(paper_id, topic, item.evidence_type, claim_text, item.source_location)
        is_placeholder = item.evidence_type == "full_text_needed"

        claims.append(Claim(
            claim_id=claim_id,
            paper_id=paper_id,
            claim_text=claim_text,
            evidence_type=item.evidence_type,
            confidence=item.confidence,
            source_location=item.source_location,
            topic=topic,
        ))

    return claims


def extract_paper_claims(
    paper: dict[str, Any],
    topic: str,
    provider: Any | None = None,
) -> tuple[list[Claim], str]:
    """Extract claims from a paper, using LLM if provider is given.

    Args:
        paper: Paper dict.
        topic: Research topic.
        provider: Optional LLM provider.

    Returns:
        Tuple of (claims, extraction_method) where extraction_method is "claw" or "deterministic".
    """
    if provider is not None:
        try:
            claims = extract_paper_claims_with_llm(paper, topic, provider)
            if claims:
                return claims, "claw"
        except (LLMProviderError, LLMValidationError) as e:
            # Fall back to deterministic extraction
            pass

    claims = deterministic_extract(paper, topic)
    return claims, "deterministic"


def _deterministic_claim_id(paper_id: str, topic: str | None, evidence_type: str, claim_text: str, source_location: str) -> str:
    """Generate a deterministic claim ID from content fields."""
    normalized = " ".join(claim_text.lower().split())
    raw = f"{paper_id}:{topic or ''}:{evidence_type}:{normalized}:{source_location}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
