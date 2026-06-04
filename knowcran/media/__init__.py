"""Media extraction and processing for figures and tables."""

from knowcran.media.extract import extract_media_assets_from_elements, MediaAsset
from knowcran.media.linker import link_media_mentions, find_caption_for_figure
from knowcran.media.table_markdown import table_to_markdown

__all__ = [
    "extract_media_assets_from_elements",
    "MediaAsset",
    "link_media_mentions",
    "find_caption_for_figure",
    "table_to_markdown",
]
