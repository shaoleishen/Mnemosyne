"""Tests for media linking functionality."""

from __future__ import annotations

import pytest

from knowcran.media.linker import (
    find_caption_for_figure,
    extract_media_references,
    link_media_mentions,
    MediaMention,
)
from knowcran.media.extract import MediaAsset
from knowcran.parsers.base import ParsedElement


class TestExtractMediaReferences:
    """Test media reference extraction from text."""

    def test_english_figure_reference(self):
        text = "As shown in Figure 1, the results indicate..."
        refs = extract_media_references(text)
        assert len(refs) == 1
        assert refs[0]["type"] == "figure"
        assert refs[0]["label"] == "Figure 1"

    def test_english_fig_reference(self):
        text = "See Fig. 1 for details."
        refs = extract_media_references(text)
        assert len(refs) == 1
        assert refs[0]["label"] == "Figure 1"

    def test_chinese_figure_reference(self):
        text = "如图1所示，结果表明..."
        refs = extract_media_references(text)
        assert len(refs) == 1
        assert refs[0]["type"] == "figure"
        assert refs[0]["label"] == "Figure 1"

    def test_table_reference(self):
        text = "Table 1 shows the summary statistics."
        refs = extract_media_references(text)
        assert len(refs) == 1
        assert refs[0]["type"] == "table"
        assert refs[0]["label"] == "Table 1"

    def test_chinese_table_reference(self):
        text = "表1显示了汇总统计。"
        refs = extract_media_references(text)
        assert len(refs) == 1
        assert refs[0]["type"] == "table"
        assert refs[0]["label"] == "Table 1"

    def test_multiple_references(self):
        text = "Figure 1 and Table 1 show the results."
        refs = extract_media_references(text)
        assert len(refs) == 2
        labels = {r["label"] for r in refs}
        assert "Figure 1" in labels
        assert "Table 1" in labels

    def test_no_references(self):
        text = "This is regular text without any figures or tables."
        refs = extract_media_references(text)
        assert len(refs) == 0


class TestFindCaptionForFigure:
    """Test caption finding for figures."""

    def test_caption_before_figure(self):
        elements = [
            ParsedElement(
                element_id="1",
                element_type="paragraph",
                text="Figure 1: Overview of the experimental setup showing the main components.",
                element_index=0,
            ),
            ParsedElement(
                element_id="2",
                element_type="figure",
                text="Figure 1",
                element_index=1,
            ),
        ]
        caption = find_caption_for_figure(elements[1], elements)
        assert caption is not None
        assert "Figure 1" in caption
        assert "Overview" in caption

    def test_caption_after_figure(self):
        elements = [
            ParsedElement(
                element_id="1",
                element_type="figure",
                text="Figure 1",
                element_index=0,
            ),
            ParsedElement(
                element_id="2",
                element_type="paragraph",
                text="Figure 1: The main results of the experiment.",
                element_index=1,
            ),
        ]
        caption = find_caption_for_figure(elements[0], elements)
        assert caption is not None
        assert "Figure 1" in caption

    def test_no_caption(self):
        elements = [
            ParsedElement(
                element_id="1",
                element_type="figure",
                text="Figure 1",
                element_index=0,
            ),
            ParsedElement(
                element_id="2",
                element_type="paragraph",
                text="Some unrelated text.",
                element_index=1,
            ),
        ]
        caption = find_caption_for_figure(elements[0], elements)
        assert caption is None


class TestLinkMediaMentions:
    """Test media mention linking."""

    def test_basic_linking(self):
        assets = [
            MediaAsset(
                media_id="media1",
                paper_id="paper1",
                asset_id="asset1",
                media_type="figure",
                figure_label="Figure 1",
            ),
        ]

        elements = [
            ParsedElement(
                element_id="elem1",
                element_type="paragraph",
                text="As shown in Figure 1, the results are significant.",
                element_index=0,
            ),
        ]

        mentions = link_media_mentions(assets, elements)
        assert len(mentions) == 1
        assert mentions[0].media_id == "media1"
        assert mentions[0].paper_id == "paper1"

    def test_multiple_mentions(self):
        assets = [
            MediaAsset(
                media_id="media1",
                paper_id="paper1",
                asset_id="asset1",
                media_type="figure",
                figure_label="Figure 1",
            ),
            MediaAsset(
                media_id="media2",
                paper_id="paper1",
                asset_id="asset1",
                media_type="table",
                figure_label="Table 1",
            ),
        ]

        elements = [
            ParsedElement(
                element_id="elem1",
                element_type="paragraph",
                text="Figure 1 shows the results. Table 1 summarizes the data.",
                element_index=0,
            ),
        ]

        mentions = link_media_mentions(assets, elements)
        assert len(mentions) == 2
        media_ids = {m.media_id for m in mentions}
        assert "media1" in media_ids
        assert "media2" in media_ids

    def test_no_mentions(self):
        assets = [
            MediaAsset(
                media_id="media1",
                paper_id="paper1",
                asset_id="asset1",
                media_type="figure",
                figure_label="Figure 1",
            ),
        ]

        elements = [
            ParsedElement(
                element_id="elem1",
                element_type="paragraph",
                text="This is regular text without any references.",
                element_index=0,
            ),
        ]

        mentions = link_media_mentions(assets, elements)
        assert len(mentions) == 0
