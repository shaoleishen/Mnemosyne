"""Discovery workflow: search, deduplicate, rank, expand."""

from __future__ import annotations

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
        score = relevance_score(rec.title, rec.abstract or "", query, rec.citation_count, rec.year, oa)
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
        console.print(f"[bold]Running {len(queries)} queries for: {question}[/bold]")

        all_papers: list[dict[str, Any]] = []
        for q in queries:
            console.print(f"  Searching: {q}")
            results = client.search_bulk(q, limit=limit)
            for r in results:
                r["_query"] = q
            all_papers.extend(results)

        deduped = _deduplicate(all_papers)
        console.print(f"  Found {len(all_papers)} raw, {len(deduped)} unique")

        ranked = _rank(deduped, question)
        for r in ranked:
            r.discovered_by = "keyword_search"

        storage.upsert_papers(ranked)
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
    expanded_papers: list[PaperRecord] = []
    failed_expansions: list[str] = []

    for paper in top_papers:
        console.print(f"  Expanding: {paper.title[:60]}...")

        # References
        try:
            detail = client.get_paper(paper.paper_id, fields="references")
            refs = detail.get("references") or []
            for ref in refs[:20]:
                ref_id = ref.get("paperId")
                if ref_id:
                    links.append(PaperLink(source_paper_id=paper.paper_id, target_paper_id=ref_id, link_type="reference"))
                    if ref.get("title"):
                        expanded_papers.append(PaperRecord.from_s2(ref, discovered_by="reference_expansion"))
        except Exception as e:
            msg = f"references for {paper.paper_id}: {e}"
            console.print(f"    [yellow]Warning: failed to fetch {msg}[/yellow]")
            failed_expansions.append(msg)

        # Citations
        try:
            detail = client.get_paper(paper.paper_id, fields="citations")
            cites = detail.get("citations") or []
            for cite in cites[:20]:
                cite_id = cite.get("paperId")
                if cite_id:
                    links.append(PaperLink(source_paper_id=paper.paper_id, target_paper_id=cite_id, link_type="citation"))
                    if cite.get("title"):
                        expanded_papers.append(PaperRecord.from_s2(cite, discovered_by="citation_expansion"))
        except Exception as e:
            msg = f"citations for {paper.paper_id}: {e}"
            console.print(f"    [yellow]Warning: failed to fetch {msg}[/yellow]")
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
                    expanded_papers.append(PaperRecord.from_s2(rec, discovered_by="recommendation"))
        except Exception as e:
            msg = f"recommendations: {e}"
            console.print(f"    [yellow]Warning: failed to fetch {msg}[/yellow]")
            failed_expansions.append(msg)

    storage.insert_links(links)
    storage.upsert_papers(expanded_papers)
    console.print(f"  Expansion: {len(expanded_papers)} papers, {len(links)} links, {len(failed_expansions)} failures")
