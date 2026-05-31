"""Robin-style structured workflow for topic research runs.

Generates structured output directories with run manifests,
paper inventories, evidence matrices, and literature reviews.
"""

from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowcran.config import Settings
from knowcran.storage import Storage


def create_output_dir(topic: str, base_dir: Path | None = None) -> Path:
    """Create a timestamped output directory for a topic run."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = topic.lower().replace(" ", "_").replace("/", "_")[:50]
    dir_name = f"{slug}_{timestamp}"
    output_dir = (base_dir or Path("mnemosyne_output")) / dir_name
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "paper_notes").mkdir(exist_ok=True)
    (output_dir / "extracted_claims").mkdir(exist_ok=True)
    return output_dir


def generate_run_manifest(
    run_id: str,
    topic: str,
    output_dir: Path,
    paper_count: int,
    pdf_count: int,
    parsed_count: int,
    claim_count: int,
    status: str = "completed",
    steps: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate and write a run manifest JSON file."""
    manifest = {
        "run_id": run_id,
        "topic": topic,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "paper_count": paper_count,
        "pdf_count": pdf_count,
        "parsed_count": parsed_count,
        "claim_count": claim_count,
        "output_dir": str(output_dir),
        "steps": steps or {},
    }
    manifest_path = output_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def generate_paper_inventory(
    papers: list[dict[str, Any]],
    output_dir: Path,
) -> Path:
    """Generate a CSV inventory of papers."""
    csv_path = output_dir / "paper_inventory.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["paper_id", "title", "year", "doi", "citation_count", "venue", "has_pdf", "has_chunks"])
        for p in papers:
            writer.writerow([
                p.get("paper_id", ""),
                p.get("title", ""),
                p.get("year", ""),
                p.get("doi", ""),
                p.get("citation_count", 0),
                p.get("venue", ""),
                p.get("has_pdf", False),
                p.get("has_chunks", False),
            ])
    return csv_path


def generate_pdf_status_csv(
    assets: list[dict[str, Any]],
    output_dir: Path,
) -> Path:
    """Generate a CSV of PDF download status."""
    csv_path = output_dir / "pdf_status.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["asset_id", "paper_id", "status", "source", "file_path", "size_bytes", "error"])
        for a in assets:
            writer.writerow([
                a.get("asset_id", ""),
                a.get("paper_id", ""),
                a.get("status", ""),
                a.get("source", ""),
                a.get("file_path", ""),
                a.get("size_bytes", ""),
                a.get("error", ""),
            ])
    return csv_path


def generate_evidence_matrix_csv(
    claims: list[dict[str, Any]],
    papers: dict[str, dict],
    output_dir: Path,
) -> Path:
    """Generate a CSV evidence matrix."""
    csv_path = output_dir / "evidence_matrix.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "paper_id", "title", "year", "claim_text", "evidence_type",
            "confidence", "evidence_status", "source_location", "citation_key",
        ])
        for c in claims:
            paper = papers.get(c.get("paper_id", ""), {})
            writer.writerow([
                c.get("paper_id", ""),
                paper.get("title", ""),
                paper.get("year", ""),
                c.get("claim_text", "")[:200],
                c.get("evidence_type", ""),
                c.get("confidence", 0),
                c.get("evidence_status", ""),
                c.get("source_location", ""),
                c.get("citation_key", ""),
            ])
    return csv_path


def generate_topic_summary(
    topic: str,
    papers: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    output_dir: Path,
) -> Path:
    """Generate a topic summary markdown file."""
    md_path = output_dir / "topic_summary.md"
    lines = [
        f"# Topic Summary: {topic}\n",
        f"Generated: {datetime.now(timezone.utc).isoformat()}\n",
        f"## Statistics\n",
        f"- Papers: {len(papers)}",
        f"- Claims: {len(claims)}",
        "",
        "## Papers\n",
    ]
    for p in papers[:20]:
        lines.append(f"- {p.get('title', 'N/A')} ({p.get('year', 'N/A')}) - {p.get('doi', 'N/A')}")
    if len(papers) > 20:
        lines.append(f"- ... and {len(papers) - 20} more")

    lines.append("\n## Claim Distribution\n")
    type_counts: dict[str, int] = {}
    for c in claims:
        etype = c.get("evidence_type", "unknown")
        type_counts[etype] = type_counts.get(etype, 0) + 1
    for etype, count in sorted(type_counts.items()):
        lines.append(f"- {etype}: {count}")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def run_topic_workflow(
    topic: str,
    limit: int = 50,
    strategy: str = "fastest",
    storage: Storage | None = None,
    settings: Settings | None = None,
    output_base: Path | None = None,
    skip_discover: bool = False,
    skip_download: bool = False,
    skip_parse: bool = False,
    skip_review: bool = False,
    fulltext: bool = True,
) -> dict[str, Any]:
    """Run the full topic research workflow.

    Pipeline: discover -> download -> parse -> extract -> notes -> matrix -> review -> bibliography -> manifest.

    Args:
        topic: Research topic
        limit: Maximum papers to process
        strategy: Download strategy (fastest, oa_first, legal_only, scihub_only)
        storage: Storage instance (optional)
        settings: Settings instance (optional)
        output_base: Base directory for output (default: mnemosyne_output)
        skip_discover: Skip discovery step
        skip_download: Skip PDF download step
        skip_parse: Skip PDF parse step
        skip_review: Skip review generation step
        fulltext: Use full-text extraction when available
    """
    settings = settings or Settings()
    storage = storage or Storage(settings.db_path)

    run_id = str(uuid.uuid4())
    canonical_topic = storage.resolve_topic(topic)
    output_dir = create_output_dir(canonical_topic, output_base)

    result = {
        "run_id": run_id,
        "topic": canonical_topic,
        "output_dir": str(output_dir),
        "status": "running",
        "steps": {},
    }

    try:
        # Step 1: Get papers (discover if needed)
        papers = storage.get_topic_papers(canonical_topic, limit=limit)
        if not papers and not skip_discover:
            # Auto-discover if no papers exist
            from knowcran.discovery import discover as do_discover
            from knowcran.semantic_scholar import SemanticScholarClient
            client = SemanticScholarClient()
            try:
                discovered = do_discover(canonical_topic, limit=limit, client=client, storage=storage)
                result["steps"]["discover"] = {"status": "completed", "count": len(discovered)}
                papers = storage.get_topic_papers(canonical_topic, limit=limit)
            except Exception as e:
                result["steps"]["discover"] = {"status": "failed", "error": str(e)}
            finally:
                client.close()
        elif skip_discover:
            result["steps"]["discover"] = {"status": "skipped"}
        else:
            result["steps"]["discover"] = {"status": "completed", "count": len(papers)}

        result["steps"]["papers"] = len(papers)

        # Step 2: Download PDFs
        if not skip_download:
            from knowcran.fulltext import download_topic_pdfs
            dl_result = download_topic_pdfs(canonical_topic, limit=limit, strategy=strategy,
                                             storage=storage, settings=settings)
            result["steps"]["download"] = dl_result
        else:
            dl_result = {"downloaded": 0, "skipped": 0, "failed": 0}
            result["steps"]["download"] = {"status": "skipped"}

        # Step 3: Parse PDFs
        if not skip_parse:
            from knowcran.fulltext import parse_topic_pdfs
            parse_result = parse_topic_pdfs(canonical_topic, limit=limit, storage=storage, settings=settings)
            result["steps"]["parse"] = parse_result
        else:
            parse_result = {"parsed": 0, "skipped": 0, "failed": 0}
            result["steps"]["parse"] = {"status": "skipped"}

        # Step 4: Extract claims (fulltext or abstract)
        from knowcran.reading import read_topic
        claims = read_topic(canonical_topic, limit=limit, storage=storage, fulltext=fulltext)
        ft_count = sum(1 for c in claims if c.evidence_status == "full_text_reviewed")
        abstract_count = len(claims) - ft_count
        result["steps"]["extract"] = {
            "status": "completed",
            "total": len(claims),
            "fulltext": ft_count,
            "abstract_only": abstract_count,
        }

        # Step 5: Generate notes
        from knowcran.notes import generate_topic_notes
        notes_result = generate_topic_notes(canonical_topic, limit=limit, storage=storage)
        result["steps"]["notes"] = notes_result

        # Step 6: Generate output artifacts
        # Paper inventory
        papers_with_status = []
        for p in papers:
            pid = p["paper_id"]
            p_copy = dict(p)
            p_copy["has_pdf"] = bool(storage.get_assets_for_paper(pid))
            p_copy["has_chunks"] = storage.has_chunks(pid)
            papers_with_status.append(p_copy)

        generate_paper_inventory(papers_with_status, output_dir)
        generate_topic_summary(canonical_topic, papers_with_status, claims, output_dir)
        generate_evidence_matrix_csv(claims, {p["paper_id"]: p for p in papers}, output_dir)

        # PDF status
        all_assets = []
        for p in papers:
            assets = storage.get_assets_for_paper(p["paper_id"])
            all_assets.extend(assets)
        generate_pdf_status_csv(all_assets, output_dir)

        # Step 7: Generate review
        if not skip_review:
            from knowcran.review import review as do_review
            from knowcran.bibtex import papers_to_bibtex
            from knowcran.utils import slugify

            output = do_review(canonical_topic, max_papers=limit, storage=storage,
                              vault_dir=settings.vault_dir, fulltext=fulltext)

            # Copy review artifacts to output directory
            slug = slugify(canonical_topic)
            reviews_dir = settings.vault_dir / "reviews"
            for name, suffix in [
                ("literature_review", f"{slug}_review.md"),
                ("evidence_matrix", f"{slug}_evidence_matrix.csv"),
                ("bibliography", f"{slug}_bibliography.bib"),
                ("open_questions", f"{slug}_open_questions.md"),
            ]:
                src = reviews_dir / suffix
                if src.exists():
                    dst = output_dir / f"{name}.md" if name.endswith("review") or name.endswith("questions") else output_dir / suffix
                    if name == "literature_review":
                        dst = output_dir / "literature_review.md"
                    elif name == "open_questions":
                        dst = output_dir / "open_questions.md"
                    else:
                        dst = output_dir / suffix
                    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

            result["steps"]["review"] = {
                "status": "completed",
                "evidence_count": len(output.evidence_matrix),
                "paper_count": len(output.paper_ids),
            }
        else:
            result["steps"]["review"] = {"status": "skipped"}

        # Step 8: Generate manifest
        manifest = generate_run_manifest(
            run_id=run_id,
            topic=canonical_topic,
            output_dir=output_dir,
            paper_count=len(papers),
            pdf_count=dl_result.get("downloaded", 0),
            parsed_count=parse_result.get("parsed", 0),
            claim_count=len(claims),
            status="completed",
            steps=result["steps"],
        )
        result["manifest"] = manifest

        # Record in DB
        storage.insert_review_run(
            run_id=run_id,
            topic=canonical_topic,
            status="completed",
            input_papers_json=json.dumps({"count": len(papers)}),
            input_claims_json=json.dumps({"count": len(claims), "fulltext": ft_count, "abstract": abstract_count}),
            output_dir=str(output_dir),
        )

        result["status"] = "completed"

    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        storage.insert_review_run(run_id=run_id, topic=topic, status="failed")

    return result
