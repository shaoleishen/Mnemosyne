"""Evidence extraction from papers, with optional agent-powered extraction."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from knowcran.llm.base import LLMProviderError, LLMValidationError
from knowcran.models import Claim
from knowcran.reading import _extract_claims as deterministic_extract


def extract_paper_claims_with_agent(
    paper: dict[str, Any],
    topic: str,
    agent_provider: Any,
    storage: Any = None,
) -> list[Claim]:
    """Extract claims from a paper using an agent provider.

    Args:
        paper: Paper dict with paper_id, title, abstract.
        topic: Research topic.
        agent_provider: Agent provider instance.
        storage: Optional storage for audit logging.

    Returns:
        List of Claim objects extracted by the agent.
    """
    from knowcran.agents.audit import audit_agent_run
    from knowcran.agents.schemas import AgentTask

    task = AgentTask(
        task_id=f"extract-{uuid.uuid4().hex[:8]}",
        task_type="claim_extraction",
        topic=topic,
        paper_id=paper["paper_id"],
        input_json={"topic": topic, "paper": paper, "source_text": paper.get("abstract")},
        output_schema_name="PaperExtractionOutput",
    )
    result = agent_provider.run(task)

    if storage is not None:
        audit_agent_run(task, result, storage)

    if result.status != "ok" or not result.output_json:
        return []

    return _parse_extraction_output(result.output_json, paper, topic)


def extract_paper_claims_with_llm(
    paper: dict[str, Any],
    topic: str,
    provider: Any,
) -> list[Claim]:
    """Extract claims from a paper using LLM-powered extraction (legacy)."""
    from knowcran.llm.prompts import build_extraction_prompt
    from knowcran.llm.schemas import PaperExtractionOutput
    from knowcran.utils import citation_key as gen_citation_key

    prompt = build_extraction_prompt(topic, paper)
    result = provider.call(prompt, task_type="extraction")
    parsed = PaperExtractionOutput.model_validate(result)

    claims: list[Claim] = []
    paper_id = paper["paper_id"]
    ck = gen_citation_key(paper)

    for item in parsed.evidence_items:
        claim_text = item.claim_text.strip()
        if not claim_text:
            continue

        claim_id = _deterministic_claim_id(paper_id, topic, item.evidence_type, claim_text, item.source_location)

        claims.append(Claim(
            claim_id=claim_id,
            paper_id=paper_id,
            claim_text=claim_text,
            evidence_type=item.evidence_type,
            confidence=item.confidence,
            source_location=item.source_location,
            topic=topic,
            citation_key=getattr(item, "citation_key", None) or ck,
            evidence_status=getattr(item, "evidence_status", "abstract_only"),
            source_quote=getattr(item, "source_quote", None) or (claim_text if item.source_location != "abstract" else ""),
            source_span_json=getattr(item, "source_span_json", None),
        ))

    return claims


def _parse_extraction_output(output: dict[str, Any], paper: dict[str, Any], topic: str) -> list[Claim]:
    """Parse agent extraction output into Claim objects."""
    from knowcran.utils import citation_key as gen_citation_key
    claims: list[Claim] = []
    paper_id = paper["paper_id"]
    ck = gen_citation_key(paper)

    for item in output.get("evidence_items", []):
        claim_text = item.get("claim_text", "").strip()
        if not claim_text:
            continue

        evidence_type = item.get("evidence_type", "abstract_summary")
        claim_id = _deterministic_claim_id(paper_id, topic, evidence_type, claim_text, item.get("source_location", "abstract"))

        claims.append(Claim(
            claim_id=claim_id,
            paper_id=paper_id,
            claim_text=claim_text,
            evidence_type=evidence_type,
            confidence=item.get("confidence", 0.5),
            source_location=item.get("source_location", "abstract"),
            topic=topic,
            citation_key=item.get("citation_key") or ck,
            evidence_status=item.get("evidence_status") or "abstract_only",
            source_quote=item.get("source_quote") or (claim_text if item.get("source_location") != "abstract" else ""),
            source_span_json=item.get("source_span_json"),
        ))

    return claims


def extract_paper_claims(
    paper: dict[str, Any],
    topic: str,
    provider: Any | None = None,
    agent_provider: Any | None = None,
    storage: Any | None = None,
) -> tuple[list[Claim], str]:
    """Extract claims from a paper, using agent/LLM if available.

    Args:
        paper: Paper dict.
        topic: Research topic.
        provider: Optional legacy LLM provider.
        agent_provider: Optional agent provider.
        storage: Optional storage for audit.

    Returns:
        Tuple of (claims, extraction_method).
    """
    # Try agent provider first
    if agent_provider is not None:
        try:
            claims = extract_paper_claims_with_agent(paper, topic, agent_provider, storage)
            if claims:
                return claims, f"agent:{agent_provider.name}"
        except Exception:
            pass

    # Try legacy LLM provider
    if provider is not None:
        try:
            claims = extract_paper_claims_with_llm(paper, topic, provider)
            if claims:
                return claims, "claw"
        except (LLMProviderError, LLMValidationError):
            pass

    # Fallback to deterministic
    claims = deterministic_extract(paper, topic)
    return claims, "deterministic"


def _deterministic_claim_id(paper_id: str, topic: str | None, evidence_type: str, claim_text: str, source_location: str) -> str:
    """Generate a deterministic claim ID from content fields."""
    normalized = " ".join(claim_text.lower().split())
    raw = f"{paper_id}:{topic or ''}:{evidence_type}:{normalized}:{source_location}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
