"""Full-text API - orchestrates PDF download, parsing, and storage.

Provides high-level functions for downloading PDFs, parsing them into
chunks, and storing the results in the database. This is the main
interface used by CLI commands and MCP tools.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowcran.config import Settings
from knowcran.models import Claim
from knowcran.pdf_parse import parse_pdf, ParseResult
from knowcran.storage import Storage

logger = logging.getLogger(__name__)


def download_paper_pdf(
    paper_id: str,
    strategy: str = "fastest",
    storage: Storage | None = None,
    settings: Settings | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Download a PDF for a single paper.

    Resolution order: DOI -> arXiv ID -> open_access_pdf_json -> URL.
    Returns a dict with success status, source, file path, and error details.
    """
    settings = settings or Settings()
    storage = storage or Storage(settings.db_path)

    paper = storage.get_paper(paper_id)
    if not paper:
        return {"success": False, "error": f"Paper not found: {paper_id}"}

    # Check for existing successful download
    if not force:
        existing = storage.get_assets_for_paper(paper_id)
        for asset in existing:
            if asset["status"] == "downloaded" and asset.get("file_path"):
                path = Path(asset["file_path"])
                if path.exists():
                    return {
                        "success": True,
                        "source": asset.get("source", "cache"),
                        "file": str(path),
                        "asset_id": asset["asset_id"],
                        "message": "Already downloaded",
                    }

    # Extract identifiers
    doi = paper.get("doi")
    arxiv_id = paper.get("arxiv_id")
    title = paper.get("title")

    # Try to get open access PDF URL from metadata
    oa_pdf_url = None
    oa_json = paper.get("open_access_pdf_json")
    if oa_json:
        try:
            oa_data = json.loads(oa_json) if isinstance(oa_json, str) else oa_json
            if isinstance(oa_data, dict):
                oa_pdf_url = oa_data.get("url")
        except (json.JSONDecodeError, TypeError):
            pass

    # Try direct OA URL first if available
    if oa_pdf_url:
        from knowcran.paper_fetch.sources.direct_url import try_direct_url
        from knowcran.paper_fetch.pdf_utils import validate_pdf, safe_filename, compute_sha256
        from knowcran.paper_fetch.cache import PDFCache

        data, error = try_direct_url(oa_pdf_url, doi=doi, arxiv_id=arxiv_id)
        if data:
            valid, val_err = validate_pdf(data)
            if valid:
                # Store in cache
                cache = PDFCache(settings.pdf_dir)
                filename = safe_filename(title or "", doi)
                file_path = str(cache.store(data, filename))
                sha256 = compute_sha256(data)

                asset_id = str(uuid.uuid4())
                storage.insert_paper_asset(
                    asset_id=asset_id,
                    paper_id=paper_id,
                    doi=doi,
                    arxiv_id=arxiv_id,
                    file_path=file_path,
                    source="DirectUrl",
                    strategy=strategy,
                    status="downloaded",
                    sha256=sha256,
                    size_bytes=len(data),
                )
                return {
                    "success": True,
                    "identifier": doi or arxiv_id or paper_id,
                    "doi": doi,
                    "arxiv_id": arxiv_id,
                    "source": "DirectUrl",
                    "file": file_path,
                    "sha256": sha256,
                    "size_bytes": len(data),
                    "asset_id": asset_id,
                }

    from knowcran.paper_fetch.downloader import download_pdf

    result = download_pdf(
        doi=doi,
        arxiv_id=arxiv_id,
        title=title,
        paper_id=paper_id,
        strategy=strategy,
        pdf_dir=str(settings.pdf_dir),
        scihub_enabled=settings.scihub_enabled,
        libgen_enabled=settings.libgen_enabled,
        force=force,
    )

    # Record in database
    asset_id = result.asset_id
    storage.insert_paper_asset(
        asset_id=asset_id,
        paper_id=paper_id,
        doi=doi,
        arxiv_id=arxiv_id,
        file_path=result.file_path,
        source=result.source,
        strategy=strategy,
        status="downloaded" if result.success else "failed",
        error=result.error,
        sha256=result.sha256,
        size_bytes=result.size_bytes,
    )

    return result.to_dict()


def download_topic_pdfs(
    topic: str,
    limit: int = 20,
    strategy: str = "fastest",
    storage: Storage | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Download PDFs for all papers in a topic.

    Returns summary of download results.
    """
    settings = settings or Settings()
    storage = storage or Storage(settings.db_path)

    canonical_topic = storage.resolve_topic(topic)
    papers = storage.get_topic_papers(canonical_topic, limit=limit)

    results = {
        "topic": canonical_topic,
        "total_papers": len(papers),
        "downloaded": 0,
        "failed": 0,
        "skipped": 0,
        "details": [],
    }

    for paper in papers:
        pid = paper["paper_id"]
        detail = download_paper_pdf(
            paper_id=pid,
            strategy=strategy,
            storage=storage,
            settings=settings,
        )
        results["details"].append(detail)
        if detail.get("success"):
            if detail.get("message") == "Already downloaded":
                results["skipped"] += 1
            else:
                results["downloaded"] += 1
        else:
            results["failed"] += 1

    return results


def get_pdf_status(
    topic: str | None = None,
    paper_id: str | None = None,
    storage: Storage | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Get PDF download status for a topic or paper."""
    settings = settings or Settings()
    storage = storage or Storage(settings.db_path)

    if paper_id:
        assets = storage.get_assets_for_paper(paper_id)
        paper = storage.get_paper(paper_id)
        return {
            "paper_id": paper_id,
            "title": paper.get("title") if paper else None,
            "assets": assets,
            "has_pdf": any(a["status"] == "downloaded" for a in assets),
        }

    if topic:
        canonical_topic = storage.resolve_topic(topic)
        return storage.get_pdf_status_summary(canonical_topic)

    return storage.get_pdf_status_summary()


def parse_paper_pdf(
    paper_id: str,
    storage: Storage | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Parse a downloaded PDF into text chunks.

    Returns parse result with chunk count and status.
    """
    settings = settings or Settings()
    storage = storage or Storage(settings.db_path)

    # Find the downloaded asset
    assets = storage.get_assets_for_paper(paper_id)
    downloaded = None
    for asset in assets:
        if asset["status"] == "downloaded" and asset.get("file_path"):
            path = Path(asset["file_path"])
            if path.exists():
                downloaded = asset
                break

    if not downloaded:
        return {
            "success": False,
            "paper_id": paper_id,
            "error": "No downloaded PDF found",
        }

    # Check if already parsed
    if storage.has_chunks(paper_id):
        return {
            "success": True,
            "paper_id": paper_id,
            "chunk_count": storage.count_chunks_for_paper(paper_id),
            "message": "Already parsed",
        }

    # Parse
    result = parse_pdf(
        pdf_path=downloaded["file_path"],
        paper_id=paper_id,
        asset_id=downloaded["asset_id"],
    )

    if result.success:
        # Store chunks
        chunk_dicts = [c.to_dict() for c in result.chunks]
        storage.insert_fulltext_chunks(chunk_dicts)
        # Sync FTS index
        try:
            storage.sync_chunk_fts()
        except Exception as e:
            logger.warning(f"FTS sync failed: {e}")

    return {
        "success": result.success,
        "paper_id": paper_id,
        "total_pages": result.total_pages,
        "chunk_count": len(result.chunks),
        "status": result.status,
        "error": result.error,
    }


def parse_topic_pdfs(
    topic: str,
    limit: int = 20,
    storage: Storage | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Parse all downloaded PDFs for a topic.

    Returns summary of parse results.
    """
    settings = settings or Settings()
    storage = storage or Storage(settings.db_path)

    canonical_topic = storage.resolve_topic(topic)
    papers = storage.get_topic_papers(canonical_topic, limit=limit)

    results = {
        "topic": canonical_topic,
        "total_papers": len(papers),
        "parsed": 0,
        "failed": 0,
        "skipped": 0,
        "details": [],
    }

    for paper in papers:
        pid = paper["paper_id"]
        detail = parse_paper_pdf(
            paper_id=pid,
            storage=storage,
            settings=settings,
        )
        results["details"].append(detail)
        if detail.get("success"):
            if detail.get("message") == "Already parsed":
                results["skipped"] += 1
            else:
                results["parsed"] += 1
        else:
            results["failed"] += 1

    return results


def search_fulltext(
    query: str,
    topic: str | None = None,
    paper_id: str | None = None,
    limit: int = 20,
    storage: Storage | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Search fulltext chunks using FTS5.

    Returns list of matching chunks with paper metadata.
    """
    settings = settings or Settings()
    storage = storage or Storage(settings.db_path)
    return storage.search_fulltext(query, topic=topic, paper_id=paper_id, limit=limit)
