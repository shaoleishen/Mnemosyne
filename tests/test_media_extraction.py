"""Tests for media extraction functionality."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import Mock

from knowcran.media.extract import (
    normalize_label,
    detect_media_type,
    is_media_element,
    MediaAsset,
)
from knowcran.parsers.base import ParsedElement


class TestNormalizeLabel:
    """Test label normalization."""

    def test_figure_english(self):
        assert normalize_label("Figure 1") == "Figure 1"
        assert normalize_label("Figure 1a") == "Figure 1a"
        assert normalize_label("Fig. 1") == "Figure 1"
        assert normalize_label("fig 1") == "Figure 1"
        assert normalize_label("Fig.1") == "Figure 1"

    def test_figure_chinese(self):
        assert normalize_label("图1") == "Figure 1"
        assert normalize_label("图 1") == "Figure 1"
        assert normalize_label("图1a") == "Figure 1a"

    def test_table_english(self):
        assert normalize_label("Table 1") == "Table 1"
        assert normalize_label("Table 1a") == "Table 1a"

    def test_table_chinese(self):
        assert normalize_label("表1") == "Table 1"
        assert normalize_label("表 1") == "Table 1"

    def test_invalid_label(self):
        assert normalize_label("random text") is None
        assert normalize_label("") is None
        assert normalize_label("123") is None

    def test_label_in_context(self):
        assert normalize_label("As shown in Figure 1,") == "Figure 1"
        assert normalize_label("见图1所示") == "Figure 1"


class TestDetectMediaType:
    """Test media type detection."""

    def test_figure_detection(self):
        assert detect_media_type("Figure 1") == "figure"
        assert detect_media_type("Fig. 1: Overview") == "figure"
        assert detect_media_type("图1") == "figure"

    def test_table_detection(self):
        assert detect_media_type("Table 1") == "table"
        assert detect_media_type("表1") == "table"

    def test_no_detection(self):
        assert detect_media_type("random text") is None
        assert detect_media_type("") is None


class TestIsMediaElement:
    """Test media element detection."""

    def test_figure_element_type(self):
        elem = ParsedElement(element_type="figure", text="Some figure")
        assert is_media_element(elem) is True

    def test_table_element_type(self):
        elem = ParsedElement(element_type="table", text="Some table")
        assert is_media_element(elem) is True

    def test_figure_in_text(self):
        elem = ParsedElement(element_type="paragraph", text="Figure 1 shows the results")
        assert is_media_element(elem) is True

    def test_table_in_text(self):
        elem = ParsedElement(element_type="paragraph", text="Table 1 summarizes the data")
        assert is_media_element(elem) is True

    def test_not_media(self):
        elem = ParsedElement(element_type="paragraph", text="This is regular text")
        assert is_media_element(elem) is False


class TestMediaAsset:
    """Test MediaAsset dataclass."""

    def test_creation(self):
        asset = MediaAsset(
            paper_id="test123",
            asset_id="asset456",
            media_type="figure",
            figure_label="Figure 1",
            image_path="/path/to/image.png",
        )
        assert asset.paper_id == "test123"
        assert asset.media_type == "figure"
        assert asset.figure_label == "Figure 1"

    def test_to_dict(self):
        asset = MediaAsset(
            paper_id="test123",
            asset_id="asset456",
            media_type="figure",
            figure_label="Figure 1",
        )
        d = asset.to_dict()
        assert d["paper_id"] == "test123"
        assert d["media_type"] == "figure"
        assert d["figure_label"] == "Figure 1"


class TestVisionEnrichment:
    """Test Vision API enrichment for media assets."""

    def test_table_asset_gets_markdown_and_description(self, tmp_path):
        from knowcran.fulltext import _enrich_media_assets_with_vision
        from knowcran.storage import Storage

        image_path = tmp_path / "table.png"
        image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 12)
        storage = Storage(tmp_path / "test.sqlite")
        asset = MediaAsset(
            media_id="media-table-1",
            paper_id="paper-1",
            asset_id="asset-1",
            media_type="table",
            figure_label="Table 1",
            image_path=str(image_path),
        )
        storage.insert_parsed_media_assets([asset.to_dict()])

        router = Mock()
        router.describe_media.side_effect = [
            {
                "status": "success",
                "description": "A table of outcomes.",
                "provider": "mock",
                "model": "mock-vl",
                "source_type": "auxiliary_interpretation",
            },
            {
                "status": "success",
                "description": "| Group | Outcome |\n| --- | --- |\n| A | 1 |",
                "provider": "mock",
                "model": "mock-vl",
                "source_type": "machine_extracted_table",
            },
        ]

        details = _enrich_media_assets_with_vision([asset], storage, router)

        updated = storage.get_media_asset("media-table-1")
        descriptions = storage.get_media_vlm_descriptions("media-table-1")
        assert updated["markdown_table"].startswith("| Group")
        assert updated["ocr_text"].startswith("| Group")
        assert updated["extraction_method"] == "vision_api"
        assert len(descriptions) == 1
        assert details[0]["description"].startswith("A table")
        storage.close()
