"""LangGraph RAG flow definition.

Creates and runs the RAG graph with nodes:
- retrieve: FTS-prefiltered hybrid search
- hydrate_and_filter: Separate physical evidence from auxiliary
- assemble_media_context: Attach media metadata
- format_multimodal_prompt: Build multimodal prompt
- generate_answer: Call chat API
- audit_answer: Verify evidence contract compliance
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from knowcran.rag.state import AgentState
from knowcran.rag.retrieval import retrieve
from knowcran.rag.hydrate import hydrate_and_filter
from knowcran.rag.generator import generate_answer
from knowcran.rag.audit import audit_answer
from knowcran.storage import Storage
from knowcran.config import Settings

logger = logging.getLogger(__name__)


class RAGConfig(TypedDict):
    """Configuration for the RAG flow."""
    api_base: str
    api_key: str
    model: str


def create_rag_graph(
    storage: Storage,
    settings: Settings,
    config: RAGConfig,
) -> StateGraph:
    """Create the LangGraph RAG flow.

    Args:
        storage: Storage instance
        settings: Settings instance
        config: RAG configuration with API details

    Returns:
        Compiled StateGraph
    """
    # Create the graph
    workflow = StateGraph(AgentState)

    # Add nodes with bound parameters
    def retrieve_node(state: AgentState) -> dict[str, Any]:
        return retrieve(state, storage, settings)

    def hydrate_node(state: AgentState) -> dict[str, Any]:
        return hydrate_and_filter(state, storage)

    def generate_node(state: AgentState) -> dict[str, Any]:
        return generate_answer(
            state,
            api_base=config["api_base"],
            api_key=config["api_key"],
            model=config["model"],
        )

    def audit_node(state: AgentState) -> dict[str, Any]:
        return audit_answer(state)

    # Add nodes to graph
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("hydrate_and_filter", hydrate_node)
    workflow.add_node("generate_answer", generate_node)
    workflow.add_node("audit_answer", audit_node)

    # Define edges
    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "hydrate_and_filter")
    workflow.add_edge("hydrate_and_filter", "generate_answer")
    workflow.add_edge("generate_answer", "audit_answer")
    workflow.add_edge("audit_answer", END)

    # Compile the graph
    return workflow.compile()


def run_rag_query(
    query: str,
    topic: str | None = None,
    paper_id: str | None = None,
    storage: Storage | None = None,
    settings: Settings | None = None,
    config: RAGConfig | None = None,
) -> dict[str, Any]:
    """Run a RAG query through the full pipeline.

    Args:
        query: User's question
        topic: Optional topic filter
        paper_id: Optional paper ID filter
        storage: Storage instance
        settings: Settings instance
        config: RAG configuration

    Returns:
        Dict with answer, citations, chunks, media, and audit results
    """
    settings = settings or Settings()
    storage = storage or Storage(settings.db_path)

    # Default config from settings
    if config is None:
        config = RAGConfig(
            api_base=settings.openai_api_base,
            api_key=settings.openai_api_key,
            model=settings.openai_model or "gpt-4o",
        )

    # Create and run the graph
    graph = create_rag_graph(storage, settings, config)

    # Initial state
    initial_state: AgentState = {
        "query": query,
        "topic": topic,
        "paper_id": paper_id,
        "raw_retrieved": [],
        "context_texts": [],
        "context_media": [],
        "auxiliary_context": [],
        "formatted_prompt": None,
        "final_response": "",
        "audit": {},
        "degraded_reason": None,
    }

    # Run the graph
    try:
        result = graph.invoke(initial_state)
    except Exception as e:
        logger.error(f"RAG pipeline failed: {e}")
        return {
            "answer": f"Error: {e}",
            "citations": [],
            "chunks": [],
            "media": [],
            "machine_extracted_tables": [],
            "auxiliary_interpretations": [],
            "audit": {"passed": False, "violations": [str(e)]},
            "degraded_reason": str(e),
        }

    # Extract results
    context_texts = result.get("context_texts", [])
    context_media = result.get("context_media", [])
    auxiliary_context = result.get("auxiliary_context", [])

    # Separate auxiliary context by type
    machine_tables = [
        a for a in auxiliary_context
        if a.get("source_type") == "machine_extracted_table"
    ]
    vlm_descriptions = [
        a for a in auxiliary_context
        if a.get("source_type") == "auxiliary_interpretation"
    ]

    return {
        "answer": result.get("final_response", ""),
        "citations": _extract_citations(result.get("final_response", "")),
        "chunks": context_texts,
        "media": context_media,
        "machine_extracted_tables": machine_tables,
        "auxiliary_interpretations": vlm_descriptions,
        "audit": result.get("audit", {}),
        "degraded_reason": result.get("degraded_reason"),
    }


def _extract_citations(response: str) -> list[dict[str, str]]:
    """Extract citations from the response text.

    Returns list of dicts with source_type and reference info.
    """
    import re

    citations = []
    pattern = re.compile(
        r"\[Source:\s*([^]]+?)(?:,\s*([^]]+?))?(?:,\s*([^]]+?))?\]",
        re.IGNORECASE,
    )

    for match in pattern.finditer(response):
        source_type = match.group(1).strip()
        ref1 = match.group(2).strip() if match.group(2) else ""
        ref2 = match.group(3).strip() if match.group(3) else ""

        citations.append({
            "source_type": source_type,
            "reference": f"{ref1} {ref2}".strip(),
        })

    return citations
