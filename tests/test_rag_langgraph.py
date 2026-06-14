"""Tests for LangGraph RAG flow."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch, MagicMock

from knowcran.rag.state import AgentState
from knowcran.rag.hydrate import hydrate_and_filter, PHYSICAL_SOURCE_TYPES, AUXILIARY_SOURCE_TYPES
from knowcran.rag.audit import audit_answer
from knowcran.rag.prompts import (
    RAG_SYSTEM_PROMPT,
    format_multimodal_prompt,
    format_text_only_prompt,
)


class TestAgentState:
    """Test AgentState type definition."""

    def test_state_creation(self):
        state: AgentState = {
            "query": "test query",
            "topic": None,
            "paper_id": None,
            "raw_retrieved": [],
            "context_texts": [],
            "context_media": [],
            "auxiliary_context": [],
            "formatted_prompt": None,
            "final_response": "",
            "audit": {},
            "degraded_reason": None,
        }
        assert state["query"] == "test query"
        assert state["raw_retrieved"] == []


class TestHydrateAndFilter:
    """Test hydrate_and_filter node."""

    def test_separate_physical_and_auxiliary(self):
        state: AgentState = {
            "query": "test",
            "topic": None,
            "paper_id": None,
            "raw_retrieved": [
                {"chunk_id": "1", "source_type": "physical_text", "text": "text1"},
                {"chunk_id": "2", "source_type": "physical_caption", "text": "caption1"},
                {"media_id": "m1", "source_type": "original_media", "image_path": "/path/to/img.png"},
                {"media_id": "m2", "source_type": "machine_extracted_table", "markdown_table": "| A | B |"},
                {"media_id": "m3", "source_type": "auxiliary_interpretation", "description_text": "A figure"},
            ],
            "context_texts": [],
            "context_media": [],
            "auxiliary_context": [],
            "formatted_prompt": None,
            "final_response": "",
            "audit": {},
            "degraded_reason": None,
        }

        mock_storage = Mock()
        mock_storage.get_media_context.return_value = None
        mock_storage.get_media_vlm_descriptions.return_value = []

        result = hydrate_and_filter(state, mock_storage)

        assert len(result["context_texts"]) == 2  # physical_text and physical_caption
        assert len(result["context_media"]) == 1  # original_media
        assert len(result["auxiliary_context"]) == 2  # machine_extracted_table and auxiliary_interpretation

    def test_default_to_physical_text(self):
        state: AgentState = {
            "query": "test",
            "topic": None,
            "paper_id": None,
            "raw_retrieved": [
                {"chunk_id": "1", "text": "text1"},  # No source_type
            ],
            "context_texts": [],
            "context_media": [],
            "auxiliary_context": [],
            "formatted_prompt": None,
            "final_response": "",
            "audit": {},
            "degraded_reason": None,
        }

        mock_storage = Mock()
        result = hydrate_and_filter(state, mock_storage)

        assert len(result["context_texts"]) == 1


class TestAuditAnswer:
    """Test audit_answer node."""

    def test_audit_with_citations(self):
        state: AgentState = {
            "query": "test",
            "topic": None,
            "paper_id": None,
            "raw_retrieved": [],
            "context_texts": [{"text": "test"}],
            "context_media": [],
            "auxiliary_context": [],
            "formatted_prompt": None,
            "final_response": "The answer [Source: Physical Text, Paper: Test, Page: 1] shows...",
            "audit": {},
            "degraded_reason": None,
        }

        result = audit_answer(state)
        audit = result["audit"]

        assert audit["passed"] is True
        assert audit["source_counts"]["physical_text"] == 1

    def test_audit_without_citations(self):
        state: AgentState = {
            "query": "test",
            "topic": None,
            "paper_id": None,
            "raw_retrieved": [],
            "context_texts": [{"text": "test"}],
            "context_media": [],
            "auxiliary_context": [],
            "formatted_prompt": None,
            "final_response": "The answer without any citations.",
            "audit": {},
            "degraded_reason": None,
        }

        result = audit_answer(state)
        audit = result["audit"]

        assert len(audit["warnings"]) > 0
        assert "No source citations found" in audit["warnings"][0]


class TestPrompts:
    """Test prompt formatting."""

    def test_system_prompt_contains_evidence_contract(self):
        assert "Physical Evidence" in RAG_SYSTEM_PROMPT
        assert "Auxiliary Interpretation" in RAG_SYSTEM_PROMPT
        assert "trust the physical sources" in RAG_SYSTEM_PROMPT.lower()

    def test_format_multimodal_prompt(self):
        import base64
        import tempfile
        from pathlib import Path

        image_path = Path(tempfile.mkdtemp()) / "img.png"
        image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 12)

        messages = format_multimodal_prompt(
            query="What is X?",
            context_texts=[{"title": "Paper 1", "page_start": 1, "section": "Intro", "text": "Text content"}],
            context_media=[{"figure_label": "Figure 1", "caption_text": "Caption", "image_path": str(image_path)}],
            auxiliary_context=[{"source_type": "auxiliary_interpretation", "figure_label": "Figure 1", "description_text": "Description"}],
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

        # Check that content has the expected sections
        content = messages[1]["content"]
        content_text = str(content)
        assert "Physical Text Evidence" in content_text
        assert "Original Figures/Tables" in content_text
        assert "Auxiliary Interpretation" in content_text
        assert "file://" not in content_text
        assert "data:image/png;base64," in content_text

    def test_format_text_only_prompt(self):
        messages = format_text_only_prompt(
            query="What is X?",
            context_texts=[{"title": "Paper 1", "page_start": 1, "section": "Intro", "text": "Text content"}],
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"


class TestRunRagQuery:
    """Test RAG entrypoint behavior."""

    def test_no_provider_does_not_raise_missing_openai_model(self, tmp_path):
        from knowcran.config import Settings
        from knowcran.rag.graph import run_rag_query
        from knowcran.storage import Storage

        settings = Settings(data_dir=tmp_path, vision_providers="")
        storage = Storage(tmp_path / "knowcran.sqlite")

        result = run_rag_query("What is known?", storage=storage, settings=settings)

        assert "openai_model" not in str(result)
        assert result["audit"]["passed"] is False
        assert result["degraded_reason"]
        storage.close()

    def test_mock_vision_router_generates_answer(self, tmp_path):
        from knowcran.config import Settings
        from knowcran.rag.graph import run_rag_query
        from knowcran.storage import Storage

        settings = Settings(data_dir=tmp_path, vision_providers="")
        router = Mock()
        router.chat.return_value = {
            "status": "success",
            "content": "Answer [Source: Physical Text, Paper: Test, Page: 1]",
            "provider": "mock",
            "model": "mock-model",
        }
        settings.get_vision_router = Mock(return_value=router)
        storage = Storage(tmp_path / "knowcran.sqlite")

        with patch("knowcran.rag.graph.retrieve", return_value={
            "raw_retrieved": [{"source_type": "physical_text", "title": "Test", "page_start": 1, "text": "Evidence"}],
            "degraded_reason": None,
        }):
            result = run_rag_query("What is known?", storage=storage, settings=settings)

        assert result["answer"].startswith("Answer")
        assert result["audit"]["passed"] is True
        router.chat.assert_called_once()
        storage.close()


class TestSourceTypes:
    """Test source type constants."""

    def test_physical_source_types(self):
        assert "physical_text" in PHYSICAL_SOURCE_TYPES
        assert "physical_caption" in PHYSICAL_SOURCE_TYPES
        assert "original_media" in PHYSICAL_SOURCE_TYPES

    def test_auxiliary_source_types(self):
        assert "machine_extracted_table" in AUXILIARY_SOURCE_TYPES
        assert "auxiliary_interpretation" in AUXILIARY_SOURCE_TYPES
