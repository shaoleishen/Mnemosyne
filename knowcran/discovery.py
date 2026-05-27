"""Discovery workflow: search, deduplicate, rank, expand."""

from __future__ import annotations

from math import ceil
from typing import Any

from rich.console import Console

from knowcran.models import PaperLink, PaperRecord
from knowcran.semantic_scholar import SemanticScholarClient
from knowcran.storage import Storage
from knowcran.utils import generate_queries, normalize_title, relevance_score

console = Console()


def _dedup_aliases(paper: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    ext = paper.get("externalIds") or {}
    pid = paper.get("paperId")
    if pid:
        aliases.add(f"pid:{pid}")
    doi = ext.get("DOI")
    if doi:
        aliases.add(f"doi:{doi.lower()}")
    pmid = ext.get("PubMed")
    if pmid:
        aliases.add(f"pmid:{pmid}")
    title = normalize_title(paper.get("title", ""))
    if title:
        aliases.add(f"title:{title}")
    return aliases


def _deduplicate(raw_papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for p in raw_papers:
        aliases = _dedup_aliases(p)
        if aliases and not aliases & seen:
            seen.update(aliases)
            result.append(p)
    return result


def _rank(papers: list[dict[str, Any]], query: str) -> list[PaperRecord]:
    records: list[tuple[float, PaperRecord]] = []
    for p in papers:
        rec = PaperRecord.from_s2(p)
        oa = bool(p.get("openAccessPdf"))
        fields = p.get("fieldsOfStudy") or []
        score = relevance_score(rec.title, rec.abstract or "", query, rec.citation_count, rec.year, oa, fields_of_study=fields)
        rec.relevance_score = score
        records.append((score, rec))
    records.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in records]


def discover(
    question: str,
    limit: int = 100,
    expand: bool = False,
    client: SemanticScholarClient | None = None,
    storage: Storage | None = None,
) -> list[PaperRecord]:
    own_client = client is None
    own_storage = storage is None
    client = client or SemanticScholarClient()
    storage = storage or Storage()

    try:
        queries = generate_queries(question)
        candidate_pool = max(20, ceil(limit * 2 / len(queries)))
        console.print(f"[bold]Running {len(queries)} queries for: {question} (limit {limit} total)[/bold]")

        all_papers: list[dict[str, Any]] = []
        for q in queries:
            console.print(f"  Searching: {q}")
            results = client.search_bulk(q, limit=candidate_pool)
            for r in results:
                r["_query"] = q
            all_papers.extend(results)

        deduped = _deduplicate(all_papers)
        console.print(f"  Found {len(all_papers)} raw, {len(deduped)} unique")

        ranked = _rank(deduped, question)[:limit]
        for r in ranked:
            r.discovered_by = "keyword_search"

        storage.upsert_papers(ranked)
        storage.insert_topic_papers(
            question,
            [p.paper_id for p in ranked],
            source="discover",
            scores=[p.relevance_score for p in ranked],
        )
        console.print(f"  Saved {len(ranked)} papers to database")

        if expand:
            _expand(ranked[:10], client, storage)

        return ranked
    finally:
        if own_client:
            client.close()
        if own_storage:
            storage.close()


def _expand(top_papers: list[PaperRecord], client: SemanticScholarClient, storage: Storage) -> None:
    links: list[PaperLink] = []
    ref_ids: list[str] = []
    cite_ids: list[str] = []
    failed_expansions: list[str] = []

    for paper in top_papers:
        console.print(f"  Expanding: {paper.title[:60]}...")

        # References - collect IDs only
        try:
            detail = client.get_paper(paper.paper_id, fields="references")
            refs = detail.get("references") or []
            for ref in refs[:20]:
                ref_id = ref.get("paperId")
                if ref_id:
                    ref_ids.append(ref_id)
                    links.append(PaperLink(source_paper_id=paper.paper_id, target_paper_id=ref_id, link_type="reference"))
        except Exception as e:
            msg = f"references for {paper.paper_id}: {e}"
            console.print(f"    [yellow]Warning: failed to fetch {msg}[/yellow]")
            failed_expansions.append(msg)

        # Citations - collect IDs only
        try:
            detail = client.get_paper(paper.paper_id, fields="citations")
            cites = detail.get("citations") or []
            for cite in cites[:20]:
                cite_id = cite.get("paperId")
                if cite_id:
                    cite_ids.append(cite_id)
                    links.append(PaperLink(source_paper_id=paper.paper_id, target_paper_id=cite_id, link_type="citation"))
        except Exception as e:
            msg = f"citations for {paper.paper_id}: {e}"
            console.print(f"    [yellow]Warning: failed to fetch {msg}[/yellow]")
            failed_expansions.append(msg)

    # Batch fetch full metadata for all expansion paper IDs
    all_expansion_ids = list(set(ref_ids + cite_ids))
    expansion_papers: list[PaperRecord] = []
    if all_expansion_ids:
        try:
            batch = client.batch_papers(all_expansion_ids)
            for data in batch:
                if data and data.get("paperId"):
                    expansion_papers.append(PaperRecord.from_s2(data, discovered_by="reference_expansion" if data["paperId"] in ref_ids else "citation_expansion"))
        except Exception as e:
            msg = f"batch fetch for expansion papers: {e}"
            console.print(f"    [yellow]Warning: {msg}[/yellow]")
            failed_expansions.append(msg)

    # Recommendations
    seed_ids = [p.paper_id for p in top_papers[:5]]
    if seed_ids:
        try:
            recs = client.get_recommendations(seed_ids)
            for rec in recs:
                rec_id = rec.get("paperId")
                if rec_id:
                    for sid in seed_ids:
                        links.append(PaperLink(source_paper_id=sid, target_paper_id=rec_id, link_type="recommendation"))
                    expansion_papers.append(PaperRecord.from_s2(rec, discovered_by="recommendation"))
        except Exception as e:
            msg = f"recommendations: {e}"
            console.print(f"    [yellow]Warning: failed to fetch {msg}[/yellow]")
            failed_expansions.append(msg)

    storage.insert_links(links)
    storage.upsert_papers(expansion_papers)
    console.print(f"  Expansion: {len(expansion_papers)} papers, {len(links)} links, {len(failed_expansions)} failures")
