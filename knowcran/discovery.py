"""Discovery workflow: search, deduplicate, rank, expand."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any

from rich.console import Console

from knowcran.config import DEFAULT_FIELDS
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
    llm_provider: Any | None = None,
    agent_provider: Any | None = None,
    resume: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> list[PaperRecord]:
    own_client = client is None
    own_storage = storage is None
    client = client or SemanticScholarClient()
    storage = storage or Storage()

    try:
        from knowcran.utils import normalize_query, query_fingerprint

        # Resolve canonical topic
        canonical_topic = storage.resolve_topic(question)

        queries = generate_queries(question)
        candidate_pool = max(20, ceil(limit * 2 / len(queries)))

        # Plan queries and check ledger
        planned_queries = []
        skipped_count = 0
        for q in queries:
            qf = query_fingerprint(q, "search_bulk", DEFAULT_FIELDS, candidate_pool)
            existing = storage.get_discovery_query(canonical_topic, qf, "search_bulk", DEFAULT_FIELDS)

            if existing and existing["status"] == "completed" and not force:
                skipped_count += 1
                continue
            elif existing and existing["status"] == "partial" and resume:
                planned_queries.append((q, qf, existing.get("cursor_token")))
            elif existing and existing["status"] in ("failed_retryable",) and resume:
                # Check if retry time has passed
                from datetime import datetime, timezone
                next_retry = existing.get("next_retry_at")
                if next_retry:
                    try:
                        retry_time = datetime.fromisoformat(next_retry)
                        if datetime.now(timezone.utc) < retry_time:
                            skipped_count += 1
                            continue
                    except ValueError:
                        pass
                planned_queries.append((q, qf, None))
            else:
                planned_queries.append((q, qf, None))

                # Register in ledger
                qid = f"{canonical_topic[:8]}-{qf[:8]}"
                storage.upsert_discovery_query(
                    qid, canonical_topic, q, normalize_query(q),
                    qf, "search_bulk", DEFAULT_FIELDS, "planned",
                )

        # If all queries already completed and not forcing, return existing topic papers
        if not planned_queries and skipped_count > 0 and not force:
            console.print(f"[bold]All {skipped_count} queries already completed for: {question}[/bold]")
            if storage.has_topic_papers(canonical_topic):
                existing_papers = storage.get_topic_papers(canonical_topic, limit=limit)
                console.print(f"  Returning {len(existing_papers)} existing topic papers")
                return []  # Return empty since papers are already in DB
            return []

        # Dry run: show what would be done
        if dry_run:
            coverage = storage.get_discovery_topic_coverage(canonical_topic)
            console.print(f"[bold]Dry run for: {question}[/bold]")
            console.print(f"  Canonical topic: {canonical_topic}")
            console.print(f"  Planned query fingerprints: {len(queries)}")
            console.print(f"  Already completed: {skipped_count}")
            console.print(f"  Will fetch: {len(planned_queries)}")
            console.print(f"  Known papers for topic: {coverage.get('total_papers', 0)}")
            return []

        console.print(f"[bold]Running {len(planned_queries)} queries for: {question} (limit {limit} total, {skipped_count} skipped)[/bold]")

        all_papers: list[dict[str, Any]] = []
        for q, qf, cursor_token in planned_queries:
            console.print(f"  Searching: {q}")
            qid = f"{canonical_topic[:8]}-{qf[:8]}"

            try:
                storage.update_discovery_query_status(qid, "running")
                results = client.search_bulk(q, limit=candidate_pool)
                for r in results:
                    r["_query"] = q
                all_papers.extend(results)
                storage.update_discovery_query_status(qid, "completed", paper_count=len(results))
            except Exception as e:
                error_msg = str(e)
                if "timeout" in error_msg.lower() or "timed out" in error_msg.lower() or "429" in error_msg:
                    # Exponential backoff with jitter: 30s * 2^attempts + random 0-15s
                    existing_q = storage.get_discovery_query(canonical_topic, qf, "search_bulk", DEFAULT_FIELDS)
                    attempts = (existing_q.get("attempts", 0) if existing_q else 0) + 1
                    backoff_seconds = min(30 * (2 ** attempts), 3600)  # Cap at 1 hour
                    jitter = random.uniform(0, 15)
                    next_retry = (datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds + jitter)).isoformat()
                    storage.update_discovery_query_status(qid, "failed_retryable", error=error_msg, next_retry_at=next_retry)
                    console.print(f"    [yellow]Retryable error (backoff {backoff_seconds:.0f}s): {error_msg}[/yellow]")
                else:
                    storage.update_discovery_query_status(qid, "failed_permanent", error=error_msg)
                    console.print(f"    [red]Failed: {error_msg}[/red]")

        deduped = _deduplicate(all_papers)
        console.print(f"  Found {len(all_papers)} raw, {len(deduped)} unique")

        ranked = _rank(deduped, question)
        for r in ranked:
            r.discovered_by = "keyword_search"

        # Filter out papers with very low relevance (tangential/irrelevant)
        min_score_threshold = 0.15
        ranked = [r for r in ranked if r.relevance_score >= min_score_threshold]
        ranked = ranked[:limit]

        # Optional agent/LLM reranking
        if agent_provider is not None:
            ranked = _agent_rerank(ranked, question, agent_provider, storage)
        elif llm_provider is not None:
            ranked = _llm_rerank(ranked, question, llm_provider, storage)

        storage.upsert_papers(ranked)
        # Use canonical_topic for topic_papers storage (the resolved alias)
        storage.insert_topic_papers(
            canonical_topic,
            [p.paper_id for p in ranked],
            source="discover",
            scores=[p.relevance_score for p in ranked],
        )

        # If user query differs from canonical, also store under user's topic
        if canonical_topic != question:
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


def _agent_rerank(papers: list[PaperRecord], topic: str, provider: Any, storage: Storage) -> list[PaperRecord]:
    """Apply agent-based reranking using BulkExecutor for chunked parallel execution.

    execute_rerank() already applies scores to the paper dicts and returns them.
    We convert PaperRecord -> dict, run execute_rerank, then map scores back.
    """
    from knowcran.agents.bulk_executor import BulkExecutor, format_workflow_summary
    from knowcran.agents.deterministic_provider import DeterministicProvider

    if not papers:
        return papers

    try:
        paper_dicts = [{"paper_id": p.paper_id, "title": p.title, "abstract": p.abstract or ""} for p in papers]

        executor = BulkExecutor(
            provider=provider,
            fallback_provider=DeterministicProvider(),
            storage=storage,
        )

        # execute_rerank returns updated paper dicts with scores applied
        updated_dicts, summary = executor.execute_rerank(topic, paper_dicts, storage)
        console.print(f"  [dim]{format_workflow_summary(summary)}[/dim]")

        # Build score map from the returned dicts (scores already applied by execute_rerank)
        score_map: dict[str, float] = {}
        for d in updated_dicts:
            pid = d.get("paper_id", "")
            score = d.get("relevance_score")
            if pid and score is not None:
                score_map[pid] = score

        # Apply scores back to PaperRecord objects
        for p in papers:
            if p.paper_id in score_map:
                p.relevance_score = score_map[p.paper_id]

        papers.sort(key=lambda x: x.relevance_score, reverse=True)
        console.print(f"  Agent reranked {len(papers)} papers via {provider.name}")

    except Exception as e:
        console.print(f"  [yellow]Agent reranking error: {e}. Keeping deterministic order.[/yellow]")

    return papers


def _llm_rerank(papers: list[PaperRecord], topic: str, provider: Any, storage: Storage) -> list[PaperRecord]:
    """Apply LLM reranking to adjust paper relevance scores."""
    from knowcran.llm.prompts import build_relevance_prompt
    from knowcran.llm.schemas import PaperRerankOutput

    if not papers:
        return papers

    try:
        paper_dicts = [{"paper_id": p.paper_id, "title": p.title, "abstract": p.abstract or ""} for p in papers]
        prompt = build_relevance_prompt(topic, paper_dicts)
        result = provider.call(prompt, task_type="relevance_rerank")
        parsed = PaperRerankOutput.model_validate(result)

        # Map LLM scores back to papers
        score_map: dict[str, float] = {}
        for d in parsed.decisions:
            if d.is_relevant:
                score_map[d.paper_id] = d.score

        for p in papers:
            if p.paper_id in score_map:
                # Blend deterministic and LLM scores
                llm_score = score_map[p.paper_id]
                p.relevance_score = round((p.relevance_score + llm_score) / 2, 4)

        # Re-sort by blended score
        papers.sort(key=lambda x: x.relevance_score, reverse=True)
        console.print(f"  LLM reranked {len(papers)} papers")

        # Store LLM rerun info
        import hashlib
        import json
        from datetime import datetime, timezone
        run_id = hashlib.sha256(f"rerank:{topic}:{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:16]
        storage.insert_llm_run(
            run_id=run_id,
            provider="claw",
            task_type="relevance_rerank",
            input_hash=hashlib.sha256(prompt.encode()).hexdigest()[:16],
            status="completed",
            parsed_output_json=json.dumps(result),
        )

    except Exception as e:
        console.print(f"  [yellow]LLM reranking failed, keeping deterministic order: {e}[/yellow]")

    return papers


def _expand(top_papers: list[PaperRecord], client: SemanticScholarClient, storage: Storage) -> None:
    links: list[PaperLink] = []
    ref_ids: list[str] = []
    cite_ids: list[str] = []
    failed_expansions: list[str] = []

    for paper in top_papers:
        console.print(f"  Expanding: {paper.title[:60]}...")

        # Fetch both references and citations in a single API call
        try:
            detail = client.get_paper(paper.paper_id, fields="references,citations")
            refs = detail.get("references") or []
            cites = detail.get("citations") or []

            for ref in refs[:20]:
                ref_id = ref.get("paperId")
                if ref_id:
                    ref_ids.append(ref_id)
                    links.append(PaperLink(source_paper_id=paper.paper_id, target_paper_id=ref_id, link_type="reference"))

            for cite in cites[:20]:
                cite_id = cite.get("paperId")
                if cite_id:
                    cite_ids.append(cite_id)
                    links.append(PaperLink(source_paper_id=paper.paper_id, target_paper_id=cite_id, link_type="citation"))
        except Exception as e:
            msg = f"references/citations for {paper.paper_id}: {e}"
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
