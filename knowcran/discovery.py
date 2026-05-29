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
    llm_provider: Any | None = None,
    agent_provider: Any | None = None,
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
        storage.insert_topic_papers(
            question,
            [p.paper_id for p in ranked],
            source="discover",
            scores=[p.relevance_score for p in ranked],
        )

        # Store topic alias if this is a subtopic query
        # e.g., "intracerebral hemorrhage anticoagulation reversal" -> "intracerebral hemorrhage"
        words = question.lower().split()
        if len(words) > 2:
            # Try to find a canonical topic that is a prefix of this query
            canonical_topics = storage.get_canonical_topics()
            for ct in canonical_topics:
                if question.startswith(ct) and question != ct:
                    storage.add_topic_alias(question, ct)
                    break

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
    """Apply agent-based reranking to adjust paper relevance scores."""
    import hashlib
    import json
    import uuid
    from datetime import datetime, timezone
    from knowcran.agents.audit import audit_agent_run
    from knowcran.agents.schemas import AgentTask

    if not papers:
        return papers

    try:
        paper_dicts = [{"paper_id": p.paper_id, "title": p.title, "abstract": p.abstract or ""} for p in papers]
        task = AgentTask(
            task_id=f"rerank-{uuid.uuid4().hex[:8]}",
            task_type="relevance_rerank",
            topic=topic,
            input_json={"topic": topic, "papers": paper_dicts},
            output_schema_name="PaperRerankOutput",
        )
        result = provider.run(task)
        audit_agent_run(task, result, storage)

        if result.status != "ok" or not result.output_json:
            console.print(f"  [yellow]Agent reranking failed: {result.error}. Keeping deterministic order.[/yellow]")
            return papers

        decisions = result.output_json.get("decisions", [])
        score_map: dict[str, float] = {}
        reason_map: dict[str, str] = {}
        for d in decisions:
            if d.get("is_relevant", True):
                score_map[d["paper_id"]] = d.get("score", 0.5)
                reason_map[d["paper_id"]] = d.get("reason", "")

        for p in papers:
            if p.paper_id in score_map:
                llm_score = score_map[p.paper_id]
                p.relevance_score = round((p.relevance_score + llm_score) / 2, 4)

        # Store agent rerun info in topic_papers
        for p in papers:
            if p.paper_id in score_map:
                storage.insert_topic_paper(
                    topic, p.paper_id, source=f"agent:{provider.name}",
                    relevance_score=p.relevance_score,
                    llm_relevance_score=score_map[p.paper_id],
                    llm_relevance_reason=reason_map.get(p.paper_id, ""),
                )

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
