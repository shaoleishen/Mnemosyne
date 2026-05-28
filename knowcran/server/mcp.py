"""MCP server implementation for KnowCran."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from knowcran.server.tools import get_all_tools, get_read_tools, get_write_tools


def _handle_search_papers(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.storage import Storage
    data_dir = params.get("data_dir")
    db_path = Path(data_dir) / "knowcran.sqlite" if data_dir else None
    storage = Storage(db_path=db_path) if db_path else Storage()
    try:
        papers = storage.get_papers_by_topic(params["query"], limit=params.get("limit", 20))
        return {"papers": papers, "count": len(papers)}
    finally:
        storage.close()


def _handle_search_claims(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.storage import Storage
    data_dir = params.get("data_dir")
    db_path = Path(data_dir) / "knowcran.sqlite" if data_dir else None
    storage = Storage(db_path=db_path) if db_path else Storage()
    try:
        claims = storage.get_claims_by_topic(params["topic"])
        return {"claims": claims, "count": len(claims)}
    finally:
        storage.close()


def _handle_get_topic_papers(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.storage import Storage
    data_dir = params.get("data_dir")
    db_path = Path(data_dir) / "knowcran.sqlite" if data_dir else None
    storage = Storage(db_path=db_path) if db_path else Storage()
    try:
        topic = params["topic"]
        limit = params.get("limit", 20)
        if storage.has_topic_papers(topic):
            papers = storage.get_topic_papers(topic, limit=limit)
        else:
            papers = storage.get_papers_by_topic(topic, limit=limit)
        return {"papers": papers, "count": len(papers)}
    finally:
        storage.close()


def _handle_get_evidence_matrix(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.models import EvidenceMatrixRow
    from knowcran.storage import Storage
    data_dir = params.get("data_dir")
    db_path = Path(data_dir) / "knowcran.sqlite" if data_dir else None
    storage = Storage(db_path=db_path) if db_path else Storage()
    try:
        topic = params["topic"]
        max_papers = params.get("max_papers", 20)
        if storage.has_topic_papers(topic):
            papers = storage.get_topic_papers(topic, limit=max_papers)
        else:
            papers = storage.get_papers_by_topic(topic, limit=max_papers)
        selected_ids = {p["paper_id"] for p in papers}
        claims = [c for c in storage.get_claims_by_topic(topic) if c["paper_id"] in selected_ids]
        paper_map = {p["paper_id"]: p for p in papers}
        matrix = []
        for c in claims:
            p = paper_map.get(c["paper_id"], {})
            matrix.append({
                "paper_id": c["paper_id"],
                "title": p.get("title", ""),
                "year": p.get("year"),
                "claim_text": c["claim_text"],
                "evidence_type": c["evidence_type"],
                "confidence": c["confidence"],
            })
        return {"evidence_matrix": matrix, "paper_count": len(papers), "claim_count": len(claims)}
    finally:
        storage.close()


def _handle_get_bibliography(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.bibtex import papers_to_bibtex
    from knowcran.storage import Storage
    data_dir = params.get("data_dir")
    db_path = Path(data_dir) / "knowcran.sqlite" if data_dir else None
    storage = Storage(db_path=db_path) if db_path else Storage()
    try:
        topic = params["topic"]
        if storage.has_topic_papers(topic):
            papers = storage.get_topic_papers(topic)
        else:
            papers = storage.get_papers_by_topic(topic)
        bibtex = papers_to_bibtex(papers)
        return {"bibtex": bibtex, "paper_count": len(papers)}
    finally:
        storage.close()


def _handle_stats(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.storage import Storage
    data_dir = params.get("data_dir")
    db_path = Path(data_dir) / "knowcran.sqlite" if data_dir else None
    storage = Storage(db_path=db_path) if db_path else Storage()
    try:
        return {
            "papers": storage.count_papers(),
            "claims": storage.count_claims(),
            "links": storage.count_links(),
        }
    finally:
        storage.close()


def _handle_discover(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.discovery import discover
    from knowcran.semantic_scholar import SemanticScholarClient
    from knowcran.storage import Storage
    data_dir = params.get("data_dir")
    db_path = Path(data_dir) / "knowcran.sqlite" if data_dir else None
    storage = Storage(db_path=db_path) if db_path else Storage()
    client = SemanticScholarClient()
    try:
        papers = discover(
            params["topic"],
            limit=params.get("limit", 100),
            expand=params.get("expand", False),
            client=client,
            storage=storage,
        )
        return {"papers": [{"paper_id": p.paper_id, "title": p.title} for p in papers], "count": len(papers)}
    finally:
        client.close()
        storage.close()


def _handle_read_topic(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.reading import read_topic
    from knowcran.storage import Storage
    data_dir = params.get("data_dir")
    db_path = Path(data_dir) / "knowcran.sqlite" if data_dir else None
    storage = Storage(db_path=db_path) if db_path else Storage()
    try:
        claims = read_topic(params["topic"], limit=params.get("limit", 20), storage=storage)
        return {"claims": [{"claim_id": c.claim_id, "evidence_type": c.evidence_type, "claim_text": c.claim_text[:200]} for c in claims], "count": len(claims)}
    finally:
        storage.close()


def _handle_read_paper(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.reading import read_paper
    from knowcran.storage import Storage
    data_dir = params.get("data_dir")
    db_path = Path(data_dir) / "knowcran.sqlite" if data_dir else None
    storage = Storage(db_path=db_path) if db_path else Storage()
    try:
        claims = read_paper(params["paper_id"], topic=params.get("topic"), storage=storage)
        return {"claims": [{"claim_id": c.claim_id, "evidence_type": c.evidence_type, "claim_text": c.claim_text[:200]} for c in claims], "count": len(claims)}
    finally:
        storage.close()


def _handle_review(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.review import review
    from knowcran.storage import Storage
    data_dir = params.get("data_dir")
    vault_dir = params.get("vault_dir")
    db_path = Path(data_dir) / "knowcran.sqlite" if data_dir else None
    storage = Storage(db_path=db_path) if db_path else Storage()
    try:
        vdir = Path(vault_dir) if vault_dir else None
        output = review(params["topic"], max_papers=params.get("max_papers", 20), storage=storage, **({"vault_dir": vdir} if vdir else {}))
        return {
            "topic": output.topic,
            "paper_count": len(output.paper_ids),
            "evidence_count": len(output.evidence_matrix),
            "open_questions": output.open_questions,
        }
    finally:
        storage.close()


def _handle_export_obsidian(params: dict[str, Any]) -> dict[str, Any]:
    from knowcran.obsidian import export_obsidian
    from knowcran.storage import Storage
    data_dir = params.get("data_dir")
    vault_dir = params.get("vault_dir")
    db_path = Path(data_dir) / "knowcran.sqlite" if data_dir else None
    storage = Storage(db_path=db_path) if db_path else Storage()
    try:
        vdir = Path(vault_dir) if vault_dir else None
        counts = export_obsidian(params["topic"], storage=storage, **({"vault_dir": vdir} if vdir else {}))
        return counts
    finally:
        storage.close()


_TOOL_HANDLERS = {
    "mnemosyne_search_papers": _handle_search_papers,
    "mnemosyne_search_claims": _handle_search_claims,
    "mnemosyne_get_topic_papers": _handle_get_topic_papers,
    "mnemosyne_get_evidence_matrix": _handle_get_evidence_matrix,
    "mnemosyne_get_bibliography": _handle_get_bibliography,
    "mnemosyne_stats": _handle_stats,
    "mnemosyne_discover": _handle_discover,
    "mnemosyne_read_topic": _handle_read_topic,
    "mnemosyne_read_paper": _handle_read_paper,
    "mnemosyne_review": _handle_review,
    "mnemosyne_export_obsidian": _handle_export_obsidian,
}


def handle_tool_call(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Handle an MCP tool call."""
    handler = _TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return handler(params)
    except Exception as e:
        return {"error": str(e)}


def serve_mcp() -> None:
    """Run the MCP server on stdin/stdout."""
    tools = get_all_tools()

    # Simple MCP protocol implementation
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "knowcran", "version": "0.1.0"},
                },
            }
        elif method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": tools},
            }
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_params = params.get("arguments", {})
            result = handle_tool_call(tool_name, tool_params)
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, default=str)}]},
            }
        else:
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()
