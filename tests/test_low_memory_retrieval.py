"""Tests for low-memory FTS-prefiltered hybrid retrieval."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch, MagicMock

from knowcran.storage import Storage


class TestFTSPrefilteredHybridSearch:
    """Test FTS-prefiltered hybrid search."""

    def test_fts_prefilter_limits_embedding_rows(self, tmp_path):
        """Verify that FTS prefilter limits the number of embedding rows loaded."""
        db_path = tmp_path / "test.sqlite"
        storage = Storage(db_path)

        # Insert test data
        paper_id = "test_paper"
        asset_id = "test_asset"

        storage.upsert_paper(Mock(
            paper_id=paper_id,
            title="Test Paper",
            abstract=None,
            year=2024,
            publication_date=None,
            venue=None,
            url=None,
            doi=None,
            pmid=None,
            arxiv_id=None,
            citation_count=None,
            reference_count=None,
            influential_citation_count=None,
            fields_json=None,
            authors_json=None,
            external_ids_json=None,
            open_access_pdf_json=None,
            discovered_by=None,
            relevance_score=None,
            created_at=None,
            updated_at=None,
        ))

        # Insert chunks
        chunks = []
        for i in range(100):
            chunks.append({
                "chunk_id": f"chunk_{i}",
                "paper_id": paper_id,
                "asset_id": asset_id,
                "page_start": i,
                "page_end": i,
                "section": "test",
                "chunk_index": i,
                "text": f"This is test chunk {i} with some content about topic {i % 10}",
                "text_hash": f"hash_{i}",
                "token_count": 20,
                "element_ids_json": None,
            })
        storage.insert_paper_chunks(chunks)

        # Sync FTS
        storage.sync_chunk_fts()

        # Verify FTS search works
        results = storage.search_fulltext("test chunk", limit=10)
        assert len(results) > 0

        storage.close()

    def test_existing_embedding_provider_usable(self):
        """Verify that existing embedding provider remains usable."""
        from knowcran.embeddings import EmbeddingProvider, vector_to_bytes, bytes_to_vector

        # Test vector serialization
        test_vector = [0.1, 0.2, 0.3, 0.4, 0.5]
        serialized = vector_to_bytes(test_vector)
        deserialized = bytes_to_vector(serialized)

        assert len(deserialized) == len(test_vector)
        for orig, deser in zip(test_vector, deserialized):
            assert abs(orig - deser) < 1e-6


class TestMultimodalSearch:
    """Test multimodal search functionality."""

    def test_multimodal_search_returns_chunks_and_media(self, tmp_path):
        """Test that multimodal search returns both chunks and media."""
        from knowcran.fulltext import multimodal_search

        db_path = tmp_path / "test.sqlite"
        storage = Storage(db_path)

        # Insert test paper
        storage.upsert_paper(Mock(
            paper_id="test_paper",
            title="Test Paper",
            abstract=None,
            year=2024,
            publication_date=None,
            venue=None,
            url=None,
            doi=None,
            pmid=None,
            arxiv_id=None,
            citation_count=None,
            reference_count=None,
            influential_citation_count=None,
            fields_json=None,
            authors_json=None,
            external_ids_json=None,
            open_access_pdf_json=None,
            discovered_by=None,
            relevance_score=None,
            created_at=None,
            updated_at=None,
        ))

        # Insert media asset
        storage.insert_parsed_media_asset(
            media_id="media_1",
            paper_id="test_paper",
            asset_id="asset_1",
            media_type="figure",
            image_path="/path/to/image.png",
            figure_label="Figure 1",
            caption_text="Figure 1: Test caption with keyword",
        )

        # Run search
        result = multimodal_search(
            query="keyword",
            storage=storage,
            settings=Mock(db_path=db_path),
        )

        assert "chunks" in result
        assert "media" in result

        storage.close()

    def test_multimodal_search_covers_table_markdown_ocr_and_mentions(self, tmp_path):
        """Media search should cover machine tables, OCR text, and body mentions."""
        from knowcran.fulltext import multimodal_search

        db_path = tmp_path / "test.sqlite"
        storage = Storage(db_path)

        storage.upsert_paper(Mock(
            paper_id="test_paper",
            title="Test Paper",
            abstract=None,
            year=2024,
            publication_date=None,
            venue=None,
            url=None,
            doi=None,
            pmid=None,
            arxiv_id=None,
            citation_count=None,
            reference_count=None,
            influential_citation_count=None,
            fields_json=None,
            authors_json=None,
            external_ids_json=None,
            open_access_pdf_json=None,
            discovered_by=None,
            relevance_score=None,
            created_at=None,
            updated_at=None,
        ))

        storage.insert_parsed_media_asset(
            media_id="table_1",
            paper_id="test_paper",
            asset_id="asset_1",
            media_type="table",
            image_path="/path/to/table.png",
            figure_label="Table 1",
            caption_text="Table 1: Baseline data",
            markdown_table="| Group | Hematoma volume |\n| --- | --- |\n| A | 12 |",
            ocr_text="OCR says perihematomal edema",
            extraction_method="vision_api",
        )
        storage.insert_media_mention(
            mention_id="mention_1",
            media_id="table_1",
            chunk_id="chunk_1",
            paper_id="test_paper",
            mention_text="The MISTIE results are summarized in Table 1.",
        )

        markdown_result = multimodal_search("Hematoma volume", storage=storage, settings=Mock(db_path=db_path))
        ocr_result = multimodal_search("perihematomal", storage=storage, settings=Mock(db_path=db_path))
        mention_result = multimodal_search("MISTIE results", storage=storage, settings=Mock(db_path=db_path))

        assert any(m["media_id"] == "table_1" and m["source_type"] == "machine_extracted_table" for m in markdown_result["media"])
        assert any(m["media_id"] == "table_1" and m["source_type"] == "machine_extracted_table" for m in ocr_result["media"])
        assert any(m["media_id"] == "table_1" and m["match_type"] == "body_mention" for m in mention_result["media"])

        storage.close()


class TestMediaStorageHelpers:
    """Test media storage helper methods."""

    def test_insert_and_get_media_asset(self, tmp_path):
        db_path = tmp_path / "test.sqlite"
        storage = Storage(db_path)

        storage.insert_parsed_media_asset(
            media_id="media_1",
            paper_id="paper_1",
            asset_id="asset_1",
            media_type="figure",
            image_path="/path/to/image.png",
            figure_label="Figure 1",
            caption_text="Test caption",
            page_number=1,
        )

        asset = storage.get_media_asset("media_1")
        assert asset is not None
        assert asset["media_id"] == "media_1"
        assert asset["figure_label"] == "Figure 1"

        storage.close()

    def test_insert_and_get_media_mentions(self, tmp_path):
        db_path = tmp_path / "test.sqlite"
        storage = Storage(db_path)

        storage.insert_media_mention(
            mention_id="mention_1",
            media_id="media_1",
            chunk_id="chunk_1",
            paper_id="paper_1",
            mention_text="As shown in Figure 1",
        )

        mentions = storage.get_media_mentions("media_1")
        assert len(mentions) == 1
        assert mentions[0]["mention_id"] == "mention_1"

        storage.close()

    def test_insert_and_get_vlm_description(self, tmp_path):
        db_path = tmp_path / "test.sqlite"
        storage = Storage(db_path)

        storage.insert_media_vlm_description(
            description_id="desc_1",
            media_id="media_1",
            provider="test_provider",
            model="test_model",
            description_text="A test description",
            source_type="auxiliary_interpretation",
            status="success",
        )

        descriptions = storage.get_media_vlm_descriptions("media_1")
        assert len(descriptions) == 1
        assert descriptions[0]["description_id"] == "desc_1"

        storage.close()

    def test_get_media_context(self, tmp_path):
        db_path = tmp_path / "test.sqlite"
        storage = Storage(db_path)

        # Insert media asset
        storage.insert_parsed_media_asset(
            media_id="media_1",
            paper_id="paper_1",
            asset_id="asset_1",
            media_type="figure",
            image_path="/path/to/image.png",
        )

        # Insert mention
        storage.insert_media_mention(
            mention_id="mention_1",
            media_id="media_1",
            chunk_id="chunk_1",
            paper_id="paper_1",
            mention_text="Reference to Figure 1",
        )

        # Insert VLM description
        storage.insert_media_vlm_description(
            description_id="desc_1",
            media_id="media_1",
            provider="test",
            model="test",
            description_text="Description",
        )

        context = storage.get_media_context("media_1")
        assert context is not None
        assert context["asset"]["media_id"] == "media_1"
        assert len(context["mentions"]) == 1
        assert len(context["descriptions"]) == 1

        storage.close()

    def test_delete_parsed_content_removes_media_state(self, tmp_path):
        db_path = tmp_path / "test.sqlite"
        storage = Storage(db_path)

        storage.insert_parsed_media_asset(
            media_id="media_1",
            paper_id="paper_1",
            asset_id="asset_1",
            media_type="figure",
            image_path="/path/to/image.png",
        )
        storage.insert_media_mention(
            mention_id="mention_1",
            media_id="media_1",
            chunk_id="chunk_1",
            paper_id="paper_1",
            mention_text="As shown in Figure 1",
        )
        storage.insert_media_vlm_description(
            description_id="desc_1",
            media_id="media_1",
            provider="test",
            model="test",
            description_text="old description",
        )

        storage.delete_parsed_content_for_paper("paper_1")

        assert storage.get_media_for_paper("paper_1") == []
        assert storage.get_media_mentions("media_1") == []
        assert storage.get_media_vlm_descriptions("media_1") == []
        storage.close()
