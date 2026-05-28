"""MCP tool definitions for KnowCran."""

from __future__ import annotations

from typing import Any


def get_read_tools() -> list[dict[str, Any]]:
    """Return read-only MCP tool definitions."""
    return [
        {
            "name": "mnemosyne_search_papers",
            "description": "Search papers in the KnowCran database by title or abstract keywords.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results", "default": 20},
                    "data_dir": {"type": "string", "description": "Data directory path"},
                },
                "required": ["query"],
            },
        },
        {
            "name": "mnemosyne_search_claims",
            "description": "Search claims by topic from the KnowCran database.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to search claims for"},
                    "data_dir": {"type": "string", "description": "Data directory path"},
                },
                "required": ["topic"],
            },
        },
        {
            "name": "mnemosyne_get_topic_papers",
            "description": "Get papers associated with a topic.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic name"},
                    "limit": {"type": "integer", "description": "Max papers", "default": 20},
                    "data_dir": {"type": "string", "description": "Data directory path"},
                },
                "required": ["topic"],
            },
        },
        {
            "name": "mnemosyne_get_evidence_matrix",
            "description": "Get the evidence matrix for a topic (papers x claims).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic name"},
                    "max_papers": {"type": "integer", "description": "Max papers", "default": 20},
                    "data_dir": {"type": "string", "description": "Data directory path"},
                },
                "required": ["topic"],
            },
        },
        {
            "name": "mnemosyne_get_bibliography",
            "description": "Get BibTeX bibliography for a topic.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic name"},
                    "data_dir": {"type": "string", "description": "Data directory path"},
                },
                "required": ["topic"],
            },
        },
        {
            "name": "mnemosyne_stats",
            "description": "Get database statistics (paper count, claim count, link count).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "data_dir": {"type": "string", "description": "Data directory path"},
                },
            },
        },
    ]


def get_write_tools() -> list[dict[str, Any]]:
    """Return write/network MCP tool definitions."""
    return [
        {
            "name": "mnemosyne_discover",
            "description": "Search Semantic Scholar for papers on a topic and store them.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Research topic or question"},
                    "limit": {"type": "integer", "description": "Max papers", "default": 100},
                    "expand": {"type": "boolean", "description": "Expand via references/citations", "default": False},
                    "data_dir": {"type": "string", "description": "Data directory path"},
                },
                "required": ["topic"],
            },
        },
        {
            "name": "mnemosyne_read_topic",
            "description": "Extract claims from all papers matching a topic.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to read"},
                    "limit": {"type": "integer", "description": "Max papers", "default": 20},
                    "data_dir": {"type": "string", "description": "Data directory path"},
                },
                "required": ["topic"],
            },
        },
        {
            "name": "mnemosyne_read_paper",
            "description": "Extract claims from a single paper.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "paper_id": {"type": "string", "description": "Semantic Scholar paper ID"},
                    "topic": {"type": "string", "description": "Topic to tag claims with"},
                    "data_dir": {"type": "string", "description": "Data directory path"},
                },
                "required": ["paper_id"],
            },
        },
        {
            "name": "mnemosyne_review",
            "description": "Generate a literature review from stored claims.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to review"},
                    "max_papers": {"type": "integer", "description": "Max papers", "default": 20},
                    "data_dir": {"type": "string", "description": "Data directory path"},
                    "vault_dir": {"type": "string", "description": "Vault directory path"},
                },
                "required": ["topic"],
            },
        },
        {
            "name": "mnemosyne_export_obsidian",
            "description": "Export Obsidian vault notes for a topic.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to export"},
                    "data_dir": {"type": "string", "description": "Data directory path"},
                    "vault_dir": {"type": "string", "description": "Vault directory path"},
                },
                "required": ["topic"],
            },
        },
    ]


def get_all_tools() -> list[dict[str, Any]]:
    """Return all MCP tools."""
    return get_read_tools() + get_write_tools()
