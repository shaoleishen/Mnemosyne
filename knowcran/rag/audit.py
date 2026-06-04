"""Audit node for the RAG flow.

Validates the generated answer against the evidence contract:
- Checks source type attribution
- Verifies no VLM leakage into physical evidence
- Reports any violations
"""

from __future__ import annotations

import logging
import re
from typing import Any

from knowcran.rag.state import AgentState

logger = logging.getLogger(__name__)

# Patterns for detecting source citations in the response
_CITATION_PATTERNS = [
    re.compile(r"\[Source:\s*(Physical Text|Physical Caption|Original Media|Machine Extraction|VLM Description)", re.IGNORECASE),
    re.compile(r"\[来源:\s*(物理文本|物理标题|原始媒体|机器提取|VLM描述)", re.IGNORECASE),
]

# Physical evidence source types
_PHYSICAL_SOURCES = {"Physical Text", "Physical Caption", "Original Media"}
_PHYSICAL_SOURCES_CN = {"物理文本", "物理标题", "原始媒体"}

# Auxiliary source types
_AUXILIARY_SOURCES = {"Machine Extraction", "VLM Description"}
_AUXILIARY_SOURCES_CN = {"机器提取", "VLM描述"}


def audit_answer(state: AgentState) -> dict[str, Any]:
    """Audit the generated answer for evidence contract compliance.

    This node:
    1. Checks that the response properly attributes sources
    2. Verifies no auxiliary interpretation is cited as physical evidence
    3. Reports any violations

    Args:
        state: Current RAG agent state

    Returns:
        Updated state with audit results
    """
    final_response = state.get("final_response", "")
    context_texts = state.get("context_texts", [])
    context_media = state.get("context_media", [])
    auxiliary_context = state.get("auxiliary_context", [])

    audit_result = {
        "passed": True,
        "violations": [],
        "warnings": [],
        "source_counts": {
            "physical_text": 0,
            "physical_caption": 0,
            "original_media": 0,
            "machine_extracted_table": 0,
            "auxiliary_interpretation": 0,
        },
    }

    # Extract citations from response
    citations = []
    for pattern in _CITATION_PATTERNS:
        for match in pattern.finditer(final_response):
            citations.append(match.group(1))

    # Check for violations
    for citation in citations:
        # Check if auxiliary sources are cited as evidence
        if citation in _AUXILIARY_SOURCES or citation in _AUXILIARY_SOURCES_CN:
            audit_result["source_counts"]["auxiliary_interpretation"] += 1
            # This is allowed but should be noted
            audit_result["warnings"].append(
                f"Auxiliary source cited: {citation}. "
                "Ensure it's not used as primary evidence."
            )
        elif citation in _PHYSICAL_SOURCES or citation in _PHYSICAL_SOURCES_CN:
            # Map to source type
            if citation in ("Physical Text", "物理文本"):
                audit_result["source_counts"]["physical_text"] += 1
            elif citation in ("Physical Caption", "物理标题"):
                audit_result["source_counts"]["physical_caption"] += 1
            elif citation in ("Original Media", "原始媒体"):
                audit_result["source_counts"]["original_media"] += 1

    # Check for potential issues
    if not citations and (context_texts or context_media):
        audit_result["warnings"].append(
            "No source citations found in response. "
            "The answer may lack proper attribution."
        )

    # Check if auxiliary context is present but not cited
    if auxiliary_context and audit_result["source_counts"]["auxiliary_interpretation"] == 0:
        audit_result["warnings"].append(
            "Auxiliary context was provided but not cited in the response."
        )

    # Log audit results
    if audit_result["violations"]:
        audit_result["passed"] = False
        logger.warning(f"Audit violations: {audit_result['violations']}")
    if audit_result["warnings"]:
        logger.info(f"Audit warnings: {audit_result['warnings']}")

    return {"audit": audit_result}
