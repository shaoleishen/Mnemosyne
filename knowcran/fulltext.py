"""Full-text API - orchestrates PDF download, parsing, and storage.

Provides high-level functions for downloading PDFs, parsing them into
chunks, and storing the results in the database. This is the main
interface used by CLI commands and MCP tools.
"""

from __future__ import annotations

import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowcran.config import Settings
from knowcran.models import Claim
from knowcran.pdf_parse import parse_pdf, ParseResult
from knowcran.storage import Storage
from knowcran.parsers import MinerUParser, PyMuPDFParser
from knowcran.parsers.base import ParsedDocument

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

    if not settings.pdf_download_enabled:
        return {
            "success": False,
            "paper_id": paper_id,
            "error": "PDF download workflow is disabled by MNEMOSYNE_PDF_DOWNLOAD_ENABLED=false",
        }

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
    pmid = paper.get("pmid")

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
                filename = safe_filename(title or "", doi=doi, arxiv_id=arxiv_id, fallback=paper_id)
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
        pmid=pmid,
        strategy=strategy,
        pdf_dir=str(settings.pdf_dir),
        scihub_enabled=settings.scihub_enabled,
        libgen_enabled=settings.libgen_enabled,
        max_workers=settings.pdf_batch_workers,
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


def _download_paper_worker(paper_id: str, strategy: str, settings: Settings) -> dict[str, Any]:
    from knowcran.storage import Storage
    storage = Storage(settings.db_path)
    try:
        return download_paper_pdf(
            paper_id=paper_id,
            strategy=strategy,
            storage=storage,
            settings=settings,
        )
    finally:
        storage.close()


def _parse_paper_worker(paper_id: str, settings: Settings) -> dict[str, Any]:
    from knowcran.storage import Storage
    storage = Storage(settings.db_path)
    try:
        return parse_paper_pdf(
            paper_id=paper_id,
            storage=storage,
            settings=settings,
        )
    finally:
        storage.close()


def download_topic_pdfs(
    topic: str,
    limit: int = 20,
    strategy: str = "fastest",
    storage: Storage | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Download PDFs for all papers in a topic concurrently.

    Returns summary of download results.
    """
    settings = settings or Settings()
    
    # We open a temporary connection to resolve the topic and get paper list
    own_storage = False
    if not storage:
        storage = Storage(settings.db_path)
        own_storage = True
        
    try:
        canonical_topic = storage.resolve_topic(topic)
        papers = storage.get_topic_papers(canonical_topic, limit=limit)
    finally:
        if own_storage:
            storage.close()

    results = {
        "topic": canonical_topic,
        "total_papers": len(papers),
        "downloaded": 0,
        "failed": 0,
        "skipped": 0,
        "details": [],
    }

    if not papers:
        return results

    if not settings.pdf_download_enabled:
        results["status"] = "disabled"
        results["message"] = "PDF download workflow is disabled by MNEMOSYNE_PDF_DOWNLOAD_ENABLED=false"
        results["skipped"] = len(papers)
        return results

    max_workers = max(1, settings.pdf_batch_workers)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_download_paper_worker, paper["paper_id"], strategy, settings): paper
            for paper in papers
        }
        completed = 0
        for future in as_completed(futures):
            paper = futures[future]
            try:
                detail = future.result()
                results["details"].append(detail)
                if detail.get("success"):
                    if detail.get("message") == "Already downloaded":
                        results["skipped"] += 1
                    else:
                        results["downloaded"] += 1
                else:
                    results["failed"] += 1
            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "success": False,
                    "paper_id": paper["paper_id"],
                    "error": f"Download thread raised exception: {e}"
                })
            completed += 1
            print(f"  PDF download progress: {completed}/{len(papers)}")

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


def _enrich_media_assets_with_vision(
    media_assets: list[Any],
    storage: Storage,
    vision_router: Any | None,
) -> list[dict[str, Any]]:
    """Generate auxiliary media descriptions and table Markdown.

    VLM descriptions and Vision-generated table Markdown remain machine
    generated context. They are stored separately from physical PDF text.
    """
    if not vision_router:
        return []

    media_descriptions = []
    for asset in media_assets:
        if not asset.image_path or not Path(asset.image_path).exists():
            continue

        # Skip very small images (e.g. less than 5KB) which are usually empty crops or tiny artifacts
        # that cause VLM prefill errors.
        try:
            if Path(asset.image_path).stat().st_size < 5120:
                logger.info(f"Skipping VLM for {asset.media_id} - image file is too small ({Path(asset.image_path).stat().st_size} bytes)")
                continue
        except Exception:
            pass

        try:
            result = vision_router.describe_media(
                image_path=asset.image_path,
                task_type="describe_media",
            )
            if result.get("status") == "success":
                storage.insert_media_vlm_description(
                    description_id=str(uuid.uuid4()),
                    media_id=asset.media_id,
                    provider=result.get("provider", "unknown"),
                    model=result.get("model", "unknown"),
                    description_text=result.get("description", ""),
                    source_type=result.get("source_type", "auxiliary_interpretation"),
                    status="success",
                )
                media_descriptions.append({
                    "media_id": asset.media_id,
                    "provider": result.get("provider"),
                    "description": result.get("description", "")[:200],
                })
                logger.info(f"Vision described {asset.figure_label or asset.media_id[:8]}")

            if asset.media_type == "table":
                from knowcran.media.table_markdown import table_to_markdown

                table_result = table_to_markdown(asset.image_path, provider=vision_router)
                markdown = table_result.get("markdown", "")
                if markdown:
                    storage.update_media_table_extraction(
                        media_id=asset.media_id,
                        markdown_table=markdown,
                        ocr_text=markdown,
                        extraction_method="vision_api",
                        confidence=table_result.get("confidence", 0.85),
                    )
                    asset.markdown_table = markdown
                    asset.ocr_text = markdown
                    asset.extraction_method = "vision_api"
                    asset.confidence = table_result.get("confidence", 0.85)
                elif table_result.get("error"):
                    logger.warning(
                        f"Vision table extraction failed for {asset.media_id}: {table_result['error']}"
                    )
        except Exception as e:
            logger.warning(f"Vision API failed for {asset.media_id}: {e}")
            try:
                storage.conn.rollback()
            except Exception:
                pass

    return media_descriptions


def parse_paper_pdf(
    paper_id: str,
    storage: Storage | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Parse a downloaded PDF into layout-aware text chunks and generate embeddings.

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

    # Choose parser based on settings
    parser_type = settings.pdf_parser
    degraded_reason = None
    if parser_type == "auto":
        from knowcran.services.manager import probe_mineru_health
        if probe_mineru_health(settings.mineru_api_url):
            logger.info("MinerU API is responsive. Selecting 'mineru' parser under 'auto' strategy.")
            parser_type = "mineru"
        else:
            logger.info("MinerU API is not responsive. Selecting 'pymupdf' parser under 'auto' strategy.")
            parser_type = "pymupdf"
            degraded_reason = "MinerU service is offline or unresponsive."
            try:
                storage.update_paper_asset(
                    downloaded["asset_id"],
                    error=f"Auto-selected PyMuPDF because MinerU API is offline."
                )
            except Exception as e:
                logger.warning(f"Failed to update asset with degraded reason: {e}")
                try:
                    storage.conn.rollback()
                except Exception:
                    pass

    parser = MinerUParser(api_url=settings.mineru_api_url, timeout=settings.mineru_timeout_seconds) if parser_type == "mineru" else PyMuPDFParser()

    logger.info(f"Parsing PDF for paper {paper_id} using {parser_type} (file: {downloaded['file_path']})")
    try:
        parsed_doc = parser.parse(Path(downloaded["file_path"]), paper_id, downloaded["asset_id"])
    except Exception as e:
        logger.error(f"Parser {parser_type} failed with exception: {e}")
        parsed_doc = ParsedDocument(
            paper_id=paper_id,
            asset_id=downloaded["asset_id"],
            parser_name=parser_type,
            parser_version="1.0.0",
            status="error",
            error=str(e),
        )

    # Fallback behavior
    if parsed_doc.status in ("error", "needs_ocr") and parser_type == "mineru":
        logger.warning(f"MinerU parsing failed: {parsed_doc.error}. Falling back to PyMuPDF.")
        try:
            storage.update_paper_asset(
                downloaded["asset_id"],
                error=f"MinerU failed: {parsed_doc.error}. Fell back to PyMuPDF."
            )
        except Exception as e:
            logger.warning(f"Failed to update asset for fallback: {e}")
            try:
                storage.conn.rollback()
            except Exception:
                pass

        fallback_parser = PyMuPDFParser()
        try:
            parsed_doc = fallback_parser.parse(Path(downloaded["file_path"]), paper_id, downloaded["asset_id"])
        except Exception as e:
            parsed_doc = ParsedDocument(
                paper_id=paper_id,
                asset_id=downloaded["asset_id"],
                parser_name="pymupdf",
                parser_version="1.0.0",
                status="error",
                error=str(e),
            )

    if parsed_doc.status == "parsed":
        storage.delete_parsed_content_for_paper(paper_id)

        # Store layout components
        storage.insert_parsed_document(
            paper_id=parsed_doc.paper_id,
            asset_id=parsed_doc.asset_id,
            parser_name=parsed_doc.parser_name,
            parser_version=parsed_doc.parser_version,
            status=parsed_doc.status,
            error=parsed_doc.error,
            source_hash=parsed_doc.source_hash,
            content_hash=parsed_doc.content_hash,
        )
        storage.insert_parsed_pages([p.to_dict() for p in parsed_doc.pages])
        storage.insert_parsed_elements([e.to_dict() for e in parsed_doc.elements])

        # --- Media extraction: figure/table screenshots + Vision API ---
        media_assets = []
        media_descriptions = []
        try:
            from knowcran.media.extract import extract_media_assets_from_elements
            from knowcran.media.linker import link_media_mentions

            pdf_path = Path(downloaded["file_path"])
            output_dir = settings.data_dir / "runtime" / "media" / paper_id

            media_assets = extract_media_assets_from_elements(
                doc=parsed_doc,
                output_dir=output_dir,
                pdf_path=pdf_path if pdf_path.exists() else None,
            )

            if media_assets:
                # Store media assets
                storage.insert_parsed_media_assets([a.to_dict() for a in media_assets])
                logger.info(f"Extracted {len(media_assets)} media assets for paper {paper_id}")

                # Link media mentions in text elements
                text_elements = [e for e in parsed_doc.elements
                                if e.element_type not in ("figure", "table", "image")]
                mentions = link_media_mentions(media_assets, text_elements)
                if mentions:
                    storage.insert_media_mentions([m.to_dict() for m in mentions])
                    logger.info(f"Linked {len(mentions)} media mentions for paper {paper_id}")

                # Vision API: describe each figure/table
                vision_router = settings.get_vision_router()
                media_descriptions = _enrich_media_assets_with_vision(
                    media_assets=media_assets,
                    storage=storage,
                    vision_router=vision_router,
                )
        except Exception as e:
            logger.warning(f"Media extraction failed for paper {paper_id}: {e}")
            try:
                storage.conn.rollback()
            except Exception:
                pass

        # Chunk elements
        from knowcran.parsers.chunker import chunk_elements
        chunks = chunk_elements(parsed_doc.elements, paper_id, downloaded["asset_id"])
        storage.insert_paper_chunks(chunks)

        # Legacy chunk support
        legacy_chunks = []
        for c in chunks:
            legacy_chunks.append({
                "chunk_id": c["chunk_id"],
                "paper_id": c["paper_id"],
                "asset_id": c["asset_id"],
                "page_start": c["page_start"],
                "page_end": c["page_end"],
                "section": c["section"],
                "chunk_index": c["chunk_index"],
                "text": c["text"],
            })
        storage.insert_fulltext_chunks(legacy_chunks)

        # Generate chunk embeddings
        embedding_status = "skipped"
        embedding_error = None
        from knowcran.embeddings import EmbeddingProvider, vector_to_bytes
        provider = EmbeddingProvider(settings)
        chunk_texts = [c["text"] for c in chunks]
        try:
            embeddings = provider.embed_texts(chunk_texts)
            emb_dicts = []
            for idx, chunk in enumerate(chunks):
                emb_bytes = vector_to_bytes(embeddings[idx])
                emb_dicts.append({
                    "chunk_id": chunk["chunk_id"],
                    "embedding_model": provider.model,
                    "embedding": emb_bytes,
                })
            storage.insert_chunk_embeddings(emb_dicts)
            embedding_status = "completed"
        except Exception as e:
            embedding_status = "failed"
            embedding_error = str(e)
            logger.error(f"Failed to generate embeddings for parsed chunks: {e}")
            try:
                storage.conn.rollback()
            except Exception:
                pass

        # Sync FTS index
        try:
            storage.sync_chunk_fts()
        except Exception as e:
            logger.warning(f"FTS sync failed: {e}")
            try:
                storage.conn.rollback()
            except Exception:
                pass

        return {
            "success": True,
            "paper_id": paper_id,
            "total_pages": len(parsed_doc.pages),
            "chunk_count": len(chunks),
            "status": parsed_doc.status,
            "error": parsed_doc.error,
            "parser": parsed_doc.parser_name,
            "degraded_reason": degraded_reason,
            "embedding_status": embedding_status,
            "embedding_error": embedding_error,
            "media_assets_extracted": len(media_assets),
            "media_descriptions_generated": len(media_descriptions),
            "media_details": media_descriptions,
        }

    return {
        "success": False,
        "paper_id": paper_id,
        "total_pages": len(parsed_doc.pages),
        "chunk_count": 0,
        "status": parsed_doc.status,
        "error": parsed_doc.error,
    }


def parse_topic_pdfs(
    topic: str,
    limit: int = 20,
    storage: Storage | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Parse all downloaded PDFs for a topic concurrently.

    Returns summary of parse results.
    """
    settings = settings or Settings()
    
    # We open a temporary connection to resolve the topic and get paper list
    own_storage = False
    if not storage:
        storage = Storage(settings.db_path)
        own_storage = True
        
    try:
        canonical_topic = storage.resolve_topic(topic)
        papers = storage.get_topic_papers(canonical_topic, limit=limit)
    finally:
        if own_storage:
            storage.close()

    results = {
        "topic": canonical_topic,
        "total_papers": len(papers),
        "parsed": 0,
        "failed": 0,
        "skipped": 0,
        "details": [],
    }

    if not papers:
        return results

    # Respect configured MinerU workers concurrency to prevent GPU OOM (RTX 3070 8GB VRAM limit)
    max_workers = max(1, settings.mineru_workers) if settings.pdf_parser in ("mineru", "auto") else 3
    if settings.mineru_gpu and max_workers > 1:
        logger.warning(
            f"GPU acceleration is active. Capping parsing workers from {max_workers} to 1 "
            "to prevent RTX 3070 8GB VRAM OOM."
        )
        max_workers = 1

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_parse_paper_worker, paper["paper_id"], settings): paper
            for paper in papers
        }
        completed = 0
        for future in as_completed(futures):
            paper = futures[future]
            try:
                detail = future.result()
                results["details"].append(detail)
                if detail.get("success"):
                    if detail.get("message") == "Already parsed":
                        results["skipped"] += 1
                    else:
                        results["parsed"] += 1
                else:
                    results["failed"] += 1
            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "success": False,
                    "paper_id": paper["paper_id"],
                    "error": f"Parse thread raised exception: {e}"
                })
            completed += 1
            print(f"  PDF parse progress: {completed}/{len(papers)}")

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


class HybridSearchResult(list):
    """Custom list subclass that carries search metadata like degraded_reason."""
    def __init__(self, items: list[dict[str, Any]], degraded_reason: str | None = None) -> None:
        super().__init__(items)
        self.degraded_reason = degraded_reason


def hybrid_search_chunks(
    query: str,
    topic: str | None = None,
    paper_id: str | None = None,
    limit: int = 20,
    storage: Storage | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Hybrid search combining SQLite FTS5 (BM25) and dense embeddings similarity.

    Uses RRF (Reciprocal Rank Fusion) and section boosts.
    """
    settings = settings or Settings()
    storage = storage or Storage(settings.db_path)

    degraded_reason = None
    query_vector = []

    # 1. Generate query embedding
    from knowcran.embeddings import EmbeddingProvider, bytes_to_vector
    provider = EmbeddingProvider(settings)
    try:
        query_vector = provider.embed_texts([query])[0]
    except Exception as e:
        logger.error(f"Failed to generate query embedding: {e}")
        degraded_reason = f"Embedding generation failed: {e}"
        query_vector = []

    if query_vector:
        # Check if database has any chunk embeddings stored
        try:
            count = storage.conn.execute(
                "SELECT count(*) FROM chunk_embeddings WHERE embedding_model = ?",
                (provider.model,)
            ).fetchone()[0]
            if count == 0:
                degraded_reason = f"No chunk embeddings found in database for model {provider.model}. Search degraded to FTS5."
        except Exception as e:
            degraded_reason = f"Failed to check chunk embeddings count: {e}"

    # 2. FTS5 BM25 search
    fts_results = storage.search_fulltext(query, topic=topic, paper_id=paper_id, limit=limit * 5)
    fts_ranks = {res["chunk_id"]: idx + 1 for idx, res in enumerate(fts_results)}
    fts_map = {res["chunk_id"]: res for res in fts_results}

    # 3. Dense embedding search
    rows = []
    if query_vector:
        if topic:
            canonical_topic = storage.resolve_topic(topic)
            rows = storage.conn.execute(
                """SELECT c.chunk_id, c.paper_id, c.page_start, c.page_end, c.section, c.chunk_index, c.text, p.title, p.year, p.doi, e.embedding
                FROM chunk_embeddings e
                INNER JOIN paper_chunks c ON e.chunk_id = c.chunk_id
                INNER JOIN papers p ON c.paper_id = p.paper_id
                INNER JOIN topic_papers tp ON c.paper_id = tp.paper_id
                WHERE tp.topic = ? AND e.embedding_model = ?""",
                (canonical_topic, provider.model),
            ).fetchall()
        elif paper_id:
            rows = storage.conn.execute(
                """SELECT c.chunk_id, c.paper_id, c.page_start, c.page_end, c.section, c.chunk_index, c.text, p.title, p.year, p.doi, e.embedding
                FROM chunk_embeddings e
                INNER JOIN paper_chunks c ON e.chunk_id = c.chunk_id
                INNER JOIN papers p ON c.paper_id = p.paper_id
                WHERE c.paper_id = ? AND e.embedding_model = ?""",
                (paper_id, provider.model),
            ).fetchall()
        else:
            rows = storage.conn.execute(
                """SELECT c.chunk_id, c.paper_id, c.page_start, c.page_end, c.section, c.chunk_index, c.text, p.title, p.year, p.doi, e.embedding
                FROM chunk_embeddings e
                INNER JOIN paper_chunks c ON e.chunk_id = c.chunk_id
                INNER JOIN papers p ON c.paper_id = p.paper_id
                WHERE e.embedding_model = ?""",
                (provider.model,),
            ).fetchall()

    vector_candidates = []
    for r in rows:
        chunk_dict = dict(r)
        emb_bytes = chunk_dict.pop("embedding")
        chunk_vector = bytes_to_vector(emb_bytes)

        sim = 0.0
        if len(query_vector) == len(chunk_vector) and len(query_vector) > 0:
            dot_prod = sum(x * y for x, y in zip(query_vector, chunk_vector))
            norm_q = sum(x * x for x in query_vector) ** 0.5
            norm_c = sum(x * x for x in chunk_vector) ** 0.5
            if norm_q > 0.0 and norm_c > 0.0:
                sim = dot_prod / (norm_q * norm_c)

        chunk_dict["similarity_score"] = sim
        vector_candidates.append(chunk_dict)

    vector_candidates.sort(key=lambda x: x["similarity_score"], reverse=True)
    vector_results = vector_candidates[:limit * 5]
    vector_ranks = {c["chunk_id"]: idx + 1 for idx, c in enumerate(vector_results)}
    vector_map = {c["chunk_id"]: c for c in vector_results}

    # 4. RRF Merging & Section Boosting
    all_chunk_ids = set(fts_ranks.keys()) | set(vector_ranks.keys())

    merged_results = []
    for cid in all_chunk_ids:
        ref_chunk = fts_map.get(cid) or vector_map.get(cid)
        if not ref_chunk:
            continue

        chunk_data = dict(ref_chunk)
        rrf_score = 0.0
        if cid in fts_ranks:
            rrf_score += 1.0 / (60.0 + fts_ranks[cid])
        if cid in vector_ranks:
            rrf_score += 1.0 / (60.0 + vector_ranks[cid])

        chunk_data["rrf_score"] = rrf_score
        chunk_data["similarity_score"] = vector_map.get(cid, {}).get("similarity_score", 0.0)
        chunk_data["fts_rank"] = fts_ranks.get(cid, None)
        chunk_data["vector_rank"] = vector_ranks.get(cid, None)

        boost = 1.0
        sec = (chunk_data.get("section") or "").lower()
        if "result" in sec:
            boost = 1.2
        elif "method" in sec:
            boost = 1.15
        elif "discussion" in sec or "conclusion" in sec:
            boost = 1.1

        chunk_data["hybrid_score"] = rrf_score * boost
        merged_results.append(chunk_data)

    merged_results.sort(key=lambda x: x["hybrid_score"], reverse=True)

    # Note on Performance Boundaries:
    # This vector search is performed in-memory on CPU using SQLite serialized BLOBs.
    # It is optimized for local research vaults (typically < 10,000 document chunks).
    # For large-scale production deployments containing > 50,000 chunks,
    # we recommend migrating the dense embedding search to a dedicated vector index
    # like pgvector, ChromaDB, or DuckDB vss.
    return HybridSearchResult(merged_results[:limit], degraded_reason=degraded_reason)


def fts_prefiltered_hybrid_search(
    query: str,
    topic: str | None = None,
    paper_id: str | None = None,
    limit: int = 20,
    fts_limit: int = 100,
    storage: Storage | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """FTS-prefiltered hybrid search for memory-efficient retrieval.

    This approach:
    1. Searches FTS5 over text chunks and media index text
    2. Selects top candidate IDs only (fts_limit)
    3. Uses the existing EmbeddingProvider to embed the query
    4. Loads embeddings only for candidate chunks/media index entries
    5. Reranks candidates using RRF

    This avoids loading all stored embedding BLOBs into memory during query.

    Args:
        query: Search query text
        topic: Optional topic filter
        paper_id: Optional paper ID filter
        limit: Maximum number of results to return
        fts_limit: Maximum number of FTS candidates to pre-filter
        storage: Storage instance
        settings: Settings instance

    Returns:
        HybridSearchResult with reranked results and degraded_reason metadata
    """
    settings = settings or Settings()
    storage = storage or Storage(settings.db_path)

    degraded_reason = None
    query_vector = []

    # 1. Generate query embedding
    from knowcran.embeddings import EmbeddingProvider, bytes_to_vector
    provider = EmbeddingProvider(settings)
    try:
        query_vector = provider.embed_texts([query])[0]
    except Exception as e:
        logger.error(f"Failed to generate query embedding: {e}")
        degraded_reason = f"Embedding generation failed: {e}"
        query_vector = []

    if query_vector:
        try:
            count = storage.conn.execute(
                "SELECT count(*) FROM chunk_embeddings WHERE embedding_model = ?",
                (provider.model,)
            ).fetchone()[0]
            if count == 0:
                degraded_reason = f"No chunk embeddings found for model {provider.model}. Search degraded to FTS5."
        except Exception as e:
            degraded_reason = f"Failed to check chunk embeddings count: {e}"

    # 2. FTS5 BM25 search - get candidate IDs
    fts_results = storage.search_fulltext(query, topic=topic, paper_id=paper_id, limit=fts_limit)
    if not fts_results:
        return HybridSearchResult([], degraded_reason=degraded_reason)

    fts_ranks = {res["chunk_id"]: idx + 1 for idx, res in enumerate(fts_results)}
    fts_map = {res["chunk_id"]: res for res in fts_results}
    candidate_ids = list(fts_ranks.keys())

    # 3. Load embeddings only for FTS candidates
    vector_candidates = []
    if query_vector and candidate_ids:
        # Build placeholders for IN clause
        placeholders = ",".join("?" * len(candidate_ids))
        rows = storage.conn.execute(
            f"""SELECT c.chunk_id, c.paper_id, c.page_start, c.page_end, c.section,
                       c.chunk_index, c.text, p.title, p.year, p.doi, e.embedding
                FROM chunk_embeddings e
                INNER JOIN paper_chunks c ON e.chunk_id = c.chunk_id
                INNER JOIN papers p ON c.paper_id = p.paper_id
                WHERE c.chunk_id IN ({placeholders}) AND e.embedding_model = ?""",
            (*candidate_ids, provider.model),
        ).fetchall()

        for r in rows:
            chunk_dict = dict(r)
            emb_bytes = chunk_dict.pop("embedding")
            chunk_vector = bytes_to_vector(emb_bytes)

            sim = 0.0
            if len(query_vector) == len(chunk_vector) and len(query_vector) > 0:
                dot_prod = sum(x * y for x, y in zip(query_vector, chunk_vector))
                norm_q = sum(x * x for x in query_vector) ** 0.5
                norm_c = sum(x * x for x in chunk_vector) ** 0.5
                if norm_q > 0.0 and norm_c > 0.0:
                    sim = dot_prod / (norm_q * norm_c)

            chunk_dict["similarity_score"] = sim
            vector_candidates.append(chunk_dict)

    vector_candidates.sort(key=lambda x: x["similarity_score"], reverse=True)
    vector_ranks = {c["chunk_id"]: idx + 1 for idx, c in enumerate(vector_candidates)}
    vector_map = {c["chunk_id"]: c for c in vector_candidates}

    # 4. RRF Merging & Section Boosting
    all_chunk_ids = set(fts_ranks.keys()) | set(vector_ranks.keys())

    merged_results = []
    for cid in all_chunk_ids:
        ref_chunk = fts_map.get(cid) or vector_map.get(cid)
        if not ref_chunk:
            continue

        chunk_data = dict(ref_chunk)
        rrf_score = 0.0
        if cid in fts_ranks:
            rrf_score += 1.0 / (60.0 + fts_ranks[cid])
        if cid in vector_ranks:
            rrf_score += 1.0 / (60.0 + vector_ranks[cid])

        chunk_data["rrf_score"] = rrf_score
        chunk_data["similarity_score"] = vector_map.get(cid, {}).get("similarity_score", 0.0)
        chunk_data["fts_rank"] = fts_ranks.get(cid, None)
        chunk_data["vector_rank"] = vector_ranks.get(cid, None)

        # Section boosting
        boost = 1.0
        sec = (chunk_data.get("section") or "").lower()
        if "result" in sec:
            boost = 1.2
        elif "method" in sec:
            boost = 1.15
        elif "discussion" in sec or "conclusion" in sec:
            boost = 1.1

        chunk_data["hybrid_score"] = rrf_score * boost
        merged_results.append(chunk_data)

    merged_results.sort(key=lambda x: x["hybrid_score"], reverse=True)

    return HybridSearchResult(merged_results[:limit], degraded_reason=degraded_reason)


def multimodal_search(
    query: str,
    topic: str | None = None,
    paper_id: str | None = None,
    limit: int = 20,
    fts_limit: int = 100,
    storage: Storage | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Multimodal search combining text chunks and media assets.

    This function:
    1. Performs FTS-prefiltered hybrid search on text chunks
    2. Searches media index text (captions, VLM descriptions, table Markdown)
    3. Combines and reranks results

    Args:
        query: Search query text
        topic: Optional topic filter
        paper_id: Optional paper ID filter
        limit: Maximum number of results
        fts_limit: FTS prefilter limit
        storage: Storage instance
        settings: Settings instance

    Returns:
        Dict with:
            - chunks: List of text chunk results
            - media: List of media asset results
            - degraded_reason: Degradation reason if any
    """
    settings = settings or Settings()
    storage = storage or Storage(settings.db_path)

    # 1. Search text chunks
    chunk_results = fts_prefiltered_hybrid_search(
        query=query,
        topic=topic,
        paper_id=paper_id,
        limit=limit,
        fts_limit=fts_limit,
        storage=storage,
        settings=settings,
    )

    # 2. Search media assets by caption, machine table extraction, OCR,
    # body mentions, and VLM descriptions.
    media_results = []
    try:
        like = f"%{query}%"

        def add_media_result(row: Any, source_type: str, match_type: str) -> None:
            media_dict = dict(row)
            media_dict["source_type"] = source_type
            media_dict["match_type"] = match_type
            media_results.append(media_dict)

        # Search in physical captions and machine-extracted table fields.
        if topic:
            canonical_topic = storage.resolve_topic(topic)
            media_rows = storage.conn.execute(
                """SELECT m.*, p.title, p.year, p.doi
                   FROM parsed_media_assets m
                   INNER JOIN papers p ON m.paper_id = p.paper_id
                   INNER JOIN topic_papers tp ON m.paper_id = tp.paper_id
                   WHERE tp.topic = ? AND (
                       m.caption_text LIKE ?
                       OR m.markdown_table LIKE ?
                       OR m.ocr_text LIKE ?
                   )
                   ORDER BY m.page_number
                   LIMIT ?""",
                (canonical_topic, like, like, like, limit),
            ).fetchall()
        elif paper_id:
            media_rows = storage.conn.execute(
                """SELECT m.*, p.title, p.year, p.doi
                   FROM parsed_media_assets m
                   INNER JOIN papers p ON m.paper_id = p.paper_id
                   WHERE m.paper_id = ? AND (
                       m.caption_text LIKE ?
                       OR m.markdown_table LIKE ?
                       OR m.ocr_text LIKE ?
                   )
                   ORDER BY m.page_number
                   LIMIT ?""",
                (paper_id, like, like, like, limit),
            ).fetchall()
        else:
            media_rows = storage.conn.execute(
                """SELECT m.*, p.title, p.year, p.doi
                   FROM parsed_media_assets m
                   INNER JOIN papers p ON m.paper_id = p.paper_id
                   WHERE m.caption_text LIKE ?
                      OR m.markdown_table LIKE ?
                      OR m.ocr_text LIKE ?
                   ORDER BY m.page_number
                   LIMIT ?""",
                (like, like, like, limit),
            ).fetchall()

        for row in media_rows:
            row_dict = dict(row)
            q = query.casefold()
            if q in (row_dict.get("markdown_table") or "").casefold():
                add_media_result(row, "machine_extracted_table", "markdown_table")
            elif q in (row_dict.get("ocr_text") or "").casefold():
                add_media_result(row, "machine_extracted_table", "ocr_text")
            else:
                add_media_result(row, "original_media", "caption")

        # Search body mentions that link text chunks to media assets.
        if topic:
            mention_rows = storage.conn.execute(
                """SELECT m.*, mm.mention_text, p.title, p.year, p.doi
                   FROM media_mentions mm
                   INNER JOIN parsed_media_assets m ON mm.media_id = m.media_id
                   INNER JOIN papers p ON m.paper_id = p.paper_id
                   INNER JOIN topic_papers tp ON m.paper_id = tp.paper_id
                   WHERE tp.topic = ? AND mm.mention_text LIKE ?
                   LIMIT ?""",
                (canonical_topic, like, limit),
            ).fetchall()
        elif paper_id:
            mention_rows = storage.conn.execute(
                """SELECT m.*, mm.mention_text, p.title, p.year, p.doi
                   FROM media_mentions mm
                   INNER JOIN parsed_media_assets m ON mm.media_id = m.media_id
                   INNER JOIN papers p ON m.paper_id = p.paper_id
                   WHERE m.paper_id = ? AND mm.mention_text LIKE ?
                   LIMIT ?""",
                (paper_id, like, limit),
            ).fetchall()
        else:
            mention_rows = storage.conn.execute(
                """SELECT m.*, mm.mention_text, p.title, p.year, p.doi
                   FROM media_mentions mm
                   INNER JOIN parsed_media_assets m ON mm.media_id = m.media_id
                   INNER JOIN papers p ON m.paper_id = p.paper_id
                   WHERE mm.mention_text LIKE ?
                   LIMIT ?""",
                (like, limit),
            ).fetchall()

        for row in mention_rows:
            add_media_result(row, "original_media", "body_mention")

        # Also search VLM descriptions
        if topic:
            vlm_rows = storage.conn.execute(
                """SELECT v.*, m.media_type, m.figure_label, m.image_path, m.page_number,
                          m.caption_text, m.markdown_table, m.ocr_text,
                          p.title, p.year, p.doi
                   FROM media_vlm_descriptions v
                   INNER JOIN parsed_media_assets m ON v.media_id = m.media_id
                   INNER JOIN papers p ON m.paper_id = p.paper_id
                   INNER JOIN topic_papers tp ON m.paper_id = tp.paper_id
                   WHERE tp.topic = ? AND v.description_text LIKE ? AND v.status = 'success'
                   LIMIT ?""",
                (canonical_topic, like, limit),
            ).fetchall()
        elif paper_id:
            vlm_rows = storage.conn.execute(
                """SELECT v.*, m.media_type, m.figure_label, m.image_path, m.page_number,
                          m.caption_text, m.markdown_table, m.ocr_text,
                          p.title, p.year, p.doi
                   FROM media_vlm_descriptions v
                   INNER JOIN parsed_media_assets m ON v.media_id = m.media_id
                   INNER JOIN papers p ON m.paper_id = p.paper_id
                   WHERE m.paper_id = ? AND v.description_text LIKE ? AND v.status = 'success'
                   LIMIT ?""",
                (paper_id, like, limit),
            ).fetchall()
        else:
            vlm_rows = storage.conn.execute(
                """SELECT v.*, m.media_type, m.figure_label, m.image_path, m.page_number,
                          m.caption_text, m.markdown_table, m.ocr_text,
                          p.title, p.year, p.doi
                   FROM media_vlm_descriptions v
                   INNER JOIN parsed_media_assets m ON v.media_id = m.media_id
                   INNER JOIN papers p ON m.paper_id = p.paper_id
                   WHERE v.description_text LIKE ? AND v.status = 'success'
                   LIMIT ?""",
                (like, limit),
            ).fetchall()

        for row in vlm_rows:
            add_media_result(row, "auxiliary_interpretation", "vlm_description")

    except Exception as e:
        logger.warning(f"Media search failed: {e}")

    # Deduplicate while preserving first-match ordering.
    deduped_media = []
    seen_media = set()
    for media in media_results:
        key = (media.get("media_id"), media.get("source_type"), media.get("match_type"))
        if key in seen_media:
            continue
        seen_media.add(key)
        deduped_media.append(media)

    return {
        "chunks": list(chunk_results),
        "media": deduped_media[:limit],
        "degraded_reason": chunk_results.degraded_reason if hasattr(chunk_results, "degraded_reason") else None,
    }
