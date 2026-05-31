"""CLI for KnowCran."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from knowcran import __version__

app = typer.Typer(name="knowcran", help="Local scientific discovery knowledge base using Semantic Scholar.")
console = Console()


def _settings(data_dir: str | None, vault_dir: str | None):
    from knowcran.config import Settings
    kwargs = {}
    if data_dir:
        kwargs["data_dir"] = Path(data_dir)
    if vault_dir:
        kwargs["vault_dir"] = Path(vault_dir)
    return Settings(**kwargs)


def _get_llm_provider(settings, use_llm: bool | None = None):
    """Get LLM provider based on settings and CLI flag."""
    from knowcran.config import Settings
    from knowcran.llm.factory import create_provider

    if use_llm is False:
        return None
    if use_llm is True:
        # Force LLM on even if default is none
        if settings.llm_provider == "none":
            settings = Settings(
                data_dir=settings.data_dir,
                vault_dir=settings.vault_dir,
                llm_provider="claw",
                claw_bin=settings.claw_bin,
                claw_model=settings.claw_model,
                claw_permission_mode=settings.claw_permission_mode,
                claw_timeout_seconds=settings.claw_timeout_seconds,
                claw_max_retries=settings.claw_max_retries,
            )
    return create_provider(settings)


def _get_agent_provider(settings, agent_provider_name: str | None = None, use_agent: bool | None = None):
    """Get agent provider based on settings and CLI flags."""
    from knowcran.agents.registry import get_registry

    if use_agent is False:
        return None

    registry = get_registry()

    if agent_provider_name:
        try:
            return registry.get(agent_provider_name)
        except Exception:
            console.print(f"[yellow]Agent provider '{agent_provider_name}' not found, using default.[/yellow]")

    if use_agent is True or agent_provider_name:
        return registry.get()

    # Auto-detect: use default if it's not deterministic
    try:
        default = registry.get()
        if default.name != "deterministic":
            return default
    except Exception:
        pass

    return None


@app.callback()
def _global_options(
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
    vault_dir: str | None = typer.Option(None, "--vault-dir", help="Vault directory path"),
) -> None:
    pass


@app.command()
def init(
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
    vault_dir: str | None = typer.Option(None, "--vault-dir", help="Vault directory path"),
) -> None:
    """Initialize data directories and database."""
    settings = _settings(data_dir, vault_dir)
    for d in [settings.data_dir, settings.raw_dir, settings.vault_dir / "papers", settings.vault_dir / "claims", settings.vault_dir / "topics", settings.vault_dir / "reviews"]:
        d.mkdir(parents=True, exist_ok=True)
    from knowcran.storage import Storage
    Storage(db_path=settings.db_path)
    console.print("[green]KnowCran initialized.[/green]")


@app.command()
def discover(
    question: str = typer.Argument(help="Disease or research question"),
    limit: int = typer.Option(100, help="Max total papers across all generated queries"),
    expand: bool = typer.Option(False, help="Expand via references/citations/recommendations"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
    vault_dir: str | None = typer.Option(None, "--vault-dir", help="Vault directory path"),
    llm: bool | None = typer.Option(None, "--llm/--no-llm", help="Enable/disable LLM reranking"),
    agent_provider: str | None = typer.Option(None, "--agent-provider", help="Agent provider name (e.g. pi-print-json, claw)"),
    resume: bool = typer.Option(False, "--resume", help="Resume from last checkpoint"),
    force: bool = typer.Option(False, "--force", help="Force re-fetch even if already completed"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done without fetching"),
) -> None:
    """Search Semantic Scholar and store papers."""
    settings = _settings(data_dir, vault_dir)
    from knowcran.discovery import discover as do_discover
    from knowcran.semantic_scholar import SemanticScholarClient
    from knowcran.storage import Storage
    client = SemanticScholarClient(api_key=settings.s2_api_key, rate_limit=settings.rate_limit_seconds, raw_dir=settings.raw_dir)
    storage = Storage(db_path=settings.db_path)
    provider = _get_agent_provider(settings, agent_provider, llm)
    llm_prov = _get_llm_provider(settings, llm) if provider is None else None
    papers = do_discover(question, limit=limit, expand=expand, client=client, storage=storage,
                         llm_provider=llm_prov, agent_provider=provider,
                         resume=resume, force=force, dry_run=dry_run)
    if not dry_run:
        console.print(f"[green]Discovered {len(papers)} papers.[/green]")


@app.command("read-paper")
def read_paper_cmd(
    paper_id: str = typer.Argument(help="Semantic Scholar paper ID"),
    topic: str | None = typer.Option(None, help="Topic to tag claims with (for review compatibility)"),
    fulltext: bool = typer.Option(False, "--fulltext", help="Use parsed PDF chunks when available, falls back to abstract"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
) -> None:
    """Extract claims from a single paper. Uses abstract by default; use --fulltext for PDF chunks."""
    settings = _settings(data_dir, None)
    from knowcran.reading import read_paper
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    claims = read_paper(paper_id, topic=topic, storage=storage, fulltext=fulltext)
    if not claims:
        console.print("[yellow]Paper not found in database.[/yellow]")
        return
    ft_count = sum(1 for c in claims if c.evidence_status == "full_text_reviewed")
    abstract_count = sum(1 for c in claims if c.evidence_status != "full_text_reviewed")
    if fulltext and ft_count > 0:
        console.print(f"[dim]Full-text claims: {ft_count}, Abstract fallback: {abstract_count}[/dim]")
    for c in claims:
        status_tag = " [full-text]" if c.evidence_status == "full_text_reviewed" else ""
        console.print(f"[bold]{c.evidence_type}[/bold] (conf {c.confidence}){status_tag}: {c.claim_text[:120]}")


@app.command("read-topic")
def read_topic_cmd(
    topic: str = typer.Argument(help="Topic to read"),
    limit: int = typer.Option(20, help="Max papers to process"),
    fulltext: bool = typer.Option(False, "--fulltext", help="Use parsed PDF chunks when available, falls back to abstract"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
    llm: bool | None = typer.Option(None, "--llm/--no-llm", help="Enable/disable LLM extraction"),
    agent_provider: str | None = typer.Option(None, "--agent-provider", help="Agent provider name"),
) -> None:
    """Extract claims from all papers matching a topic. Use --fulltext for PDF chunks."""
    settings = _settings(data_dir, None)
    from knowcran.reading import read_topic
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    agent_prov = _get_agent_provider(settings, agent_provider, llm)
    llm_prov = _get_llm_provider(settings, llm) if agent_prov is None else None
    claims = read_topic(topic, limit=limit, storage=storage, llm_provider=llm_prov, agent_provider=agent_prov, fulltext=fulltext)
    ft_count = sum(1 for c in claims if c.evidence_status == "full_text_reviewed")
    abstract_count = sum(1 for c in claims if c.evidence_status != "full_text_reviewed")
    if fulltext and ft_count > 0:
        console.print(f"[green]Extracted {len(claims)} claims: {ft_count} full-text, {abstract_count} abstract-only.[/green]")
    else:
        console.print(f"[green]Extracted {len(claims)} claims from topic papers.[/green]")


@app.command("export-obsidian")
def export_obsidian_cmd(
    topic: str = typer.Argument(help="Topic to export"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
    vault_dir: str | None = typer.Option(None, "--vault-dir", help="Vault directory path"),
) -> None:
    """Export Obsidian vault notes for a topic."""
    settings = _settings(data_dir, vault_dir)
    from knowcran.obsidian import export_obsidian
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    counts = export_obsidian(topic, storage=storage, vault_dir=settings.vault_dir)
    console.print(f"[green]Exported: {counts['papers']} papers, {counts['claims']} claims, {counts['topics']} topic notes.[/green]")


@app.command()
def review(
    topic: str = typer.Argument(help="Topic to review"),
    max_papers: int = typer.Option(20, help="Max papers for review"),
    fulltext: bool = typer.Option(False, "--fulltext", help="Prioritize full-text claims over abstract-only claims"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
    vault_dir: str | None = typer.Option(None, "--vault-dir", help="Vault directory path"),
    llm: bool | None = typer.Option(None, "--llm/--no-llm", help="Enable/disable LLM review synthesis"),
    agent_provider: str | None = typer.Option(None, "--agent-provider", help="Agent provider name"),
) -> None:
    """Generate a literature review from stored claims. Use --fulltext to prioritize full-text evidence."""
    settings = _settings(data_dir, vault_dir)
    from knowcran.review import review as do_review
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    agent_prov = _get_agent_provider(settings, agent_provider, llm)
    llm_prov = _get_llm_provider(settings, llm) if agent_prov is None else None
    output = do_review(topic, max_papers=max_papers, storage=storage, vault_dir=settings.vault_dir, llm_provider=llm_prov, agent_provider=agent_prov, fulltext=fulltext)
    console.print(f"[green]Review generated with {len(output.evidence_matrix)} evidence items and {len(output.paper_ids)} papers.[/green]")


@app.command("download-paper")
def download_paper_cmd(
    paper_id: str = typer.Argument(help="Paper ID to download PDF for"),
    strategy: str = typer.Option("fastest", help="Download strategy: fastest, oa_first, legal_only, scihub_only"),
    force: bool = typer.Option(False, "--force", help="Force re-download even if cached"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
) -> None:
    """Download a PDF for a single paper."""
    settings = _settings(data_dir, None)
    from knowcran.fulltext import download_paper_pdf
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    try:
        result = download_paper_pdf(paper_id, strategy=strategy, storage=storage, settings=settings, force=force)
        if result.get("success"):
            console.print(f"[green]Downloaded: {result.get('source')} -> {result.get('file')}[/green]")
        else:
            console.print(f"[red]Failed: {result.get('error')}[/red]")
    finally:
        storage.close()


@app.command("download-topic")
def download_topic_cmd(
    topic: str = typer.Argument(help="Topic to download PDFs for"),
    limit: int = typer.Option(20, help="Max papers to process"),
    strategy: str = typer.Option("fastest", help="Download strategy: fastest, oa_first, legal_only, scihub_only"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
) -> None:
    """Download PDFs for all papers in a topic."""
    settings = _settings(data_dir, None)
    from knowcran.fulltext import download_topic_pdfs
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    try:
        result = download_topic_pdfs(topic, limit=limit, strategy=strategy, storage=storage, settings=settings)
        console.print(f"[green]Downloaded: {result['downloaded']}, Skipped: {result['skipped']}, Failed: {result['failed']}[/green]")
    finally:
        storage.close()


@app.command("pdf-status")
def pdf_status_cmd(
    topic: str | None = typer.Argument(None, help="Topic to check PDF status for"),
    paper_id: str | None = typer.Option(None, help="Specific paper ID"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
) -> None:
    """Show PDF download status."""
    settings = _settings(data_dir, None)
    from knowcran.fulltext import get_pdf_status
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    try:
        status = get_pdf_status(topic=topic, paper_id=paper_id, storage=storage, settings=settings)
        if paper_id:
            console.print(f"[bold]Paper:[/bold] {status.get('title', 'N/A')}")
            console.print(f"[bold]Has PDF:[/bold] {status.get('has_pdf', False)}")
            for asset in status.get("assets", []):
                console.print(f"  {asset['status']}: {asset.get('source', 'N/A')} - {asset.get('file_path', 'N/A')}")
        else:
            console.print(f"[bold]Total:[/bold] {status.get('total', 0)}")
            for s, count in status.get("by_status", {}).items():
                console.print(f"  {s}: {count}")
    finally:
        storage.close()


@app.command("parse-paper")
def parse_paper_cmd(
    paper_id: str = typer.Argument(help="Paper ID to parse PDF for"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
) -> None:
    """Parse a downloaded PDF into text chunks."""
    settings = _settings(data_dir, None)
    from knowcran.fulltext import parse_paper_pdf
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    try:
        result = parse_paper_pdf(paper_id, storage=storage, settings=settings)
        if result.get("success"):
            console.print(f"[green]Parsed: {result.get('chunk_count')} chunks from {result.get('total_pages')} pages[/green]")
        else:
            console.print(f"[red]Failed: {result.get('error')}[/red]")
    finally:
        storage.close()


@app.command("parse-topic")
def parse_topic_cmd(
    topic: str = typer.Argument(help="Topic to parse PDFs for"),
    limit: int = typer.Option(20, help="Max papers to process"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
) -> None:
    """Parse all downloaded PDFs for a topic."""
    settings = _settings(data_dir, None)
    from knowcran.fulltext import parse_topic_pdfs
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    try:
        result = parse_topic_pdfs(topic, limit=limit, storage=storage, settings=settings)
        console.print(f"[green]Parsed: {result['parsed']}, Skipped: {result['skipped']}, Failed: {result['failed']}[/green]")
    finally:
        storage.close()


@app.command("search-fulltext")
def search_fulltext_cmd(
    query: str = typer.Argument(help="Search query"),
    topic: str | None = typer.Option(None, help="Scope to topic"),
    paper_id: str | None = typer.Option(None, help="Scope to paper"),
    limit: int = typer.Option(20, help="Max results"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
) -> None:
    """Search fulltext chunks using FTS5."""
    settings = _settings(data_dir, None)
    from knowcran.fulltext import search_fulltext
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    try:
        results = search_fulltext(query, topic=topic, paper_id=paper_id, limit=limit, storage=storage, settings=settings)
        if not results:
            console.print("[yellow]No results found.[/yellow]")
            return
        for r in results:
            title = r.get("title", "N/A")
            year = r.get("year", "")
            section = r.get("section", "")
            page_range = f"p.{r.get('page_start', '?')}-{r.get('page_end', '?')}"
            console.print(f"[bold]{title}[/bold] ({year}) {section} {page_range}")
            text = r.get("text", "")[:200]
            console.print(f"  {text}...")
            console.print()
    finally:
        storage.close()


@app.command("show-paper")
def show_paper_cmd(
    paper_id: str = typer.Argument(help="Paper ID to display"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
) -> None:
    """Display paper details from the database."""
    settings = _settings(data_dir, None)
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    try:
        paper = storage.get_paper(paper_id)
        if not paper:
            console.print("[yellow]Paper not found.[/yellow]")
            return
        table = Table(title=paper.get("title", ""))
        table.add_column("Field", style="bold")
        table.add_column("Value")
        for key in ["paper_id", "year", "venue", "doi", "pmid", "citation_count", "discovered_by", "relevance_score"]:
            table.add_row(key, str(paper.get(key, "")))
        console.print(table)
    finally:
        storage.close()


@app.command()
def stats(
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
) -> None:
    """Show database statistics."""
    settings = _settings(data_dir, None)
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    try:
        console.print(f"Papers:  {storage.count_papers()}")
        console.print(f"Claims:  {storage.count_claims()}")
        links = storage.count_links()
        if links == 0:
            console.print(f"Links:   {links}  (run discover --expand to collect references, citations, and recommendations)")
        else:
            console.print(f"Links:   {links}")
    finally:
        storage.close()


@app.command("llm-doctor")
def llm_doctor(
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
    live: bool = typer.Option(False, "--live", help="Run a live one-shot prompt test (uses API credits)"),
) -> None:
    """Check LLM provider configuration and connectivity."""
    from knowcran.config import Settings
    from knowcran.llm.factory import create_provider

    settings = _settings(data_dir, None)

    console.print(f"[bold]LLM Provider:[/bold] {settings.llm_provider}")
    console.print(f"[bold]Claw Model:[/bold] {settings.claw_model}")
    console.print(f"[bold]Claw Permission Mode:[/bold] {settings.claw_permission_mode}")
    console.print(f"[bold]Claw Timeout:[/bold] {settings.claw_timeout_seconds}s")
    console.print(f"[bold]Claw Max Retries:[/bold] {settings.claw_max_retries}")

    if settings.llm_provider == "none":
        console.print("[yellow]LLM provider is set to 'none'. No LLM features will be used.[/yellow]")
        console.print("Set MNEMOSYNE_LLM_PROVIDER=claw to enable LLM features.")
        return

    if settings.claw_bin:
        from pathlib import Path
        exists = Path(settings.claw_bin).exists()
        console.print(f"[bold]Claw Binary:[/bold] {settings.claw_bin}")
        if exists:
            console.print("[green]  Binary exists.[/green]")
        else:
            console.print("[red]  Binary NOT found![/red]")
    else:
        console.print("[red]No Claw binary detected![/red]")
        console.print("Set MNEMOSYNE_CLAW_BIN or ensure claw is on PATH.")

    if live:
        console.print("\n[bold]Running live test...[/bold]")
        try:
            provider = create_provider(settings)
            if provider is None:
                console.print("[yellow]Provider is None, cannot test.[/yellow]")
                return
            result = provider.call("Reply with the word READY and nothing else.", task_type="health_check")
            console.print(f"[green]Live test succeeded. Response: {str(result)[:200]}[/green]")
        except Exception as e:
            console.print(f"[red]Live test failed: {e}[/red]")





@app.command("doctor")
def doctor_cmd(
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
    live: bool = typer.Option(False, "--live", help="Run a live health check on remote services"),
) -> None:
    """Diagnose the local environment, dependencies, database, and configurations."""
    import sys
    import platform
    import sqlite3
    from knowcran.config import Settings
    from knowcran.storage import Storage

    settings = _settings(data_dir, None)

    console.print("[bold cyan]========================================[/bold cyan]")
    console.print("[bold cyan]       KnowCran System Diagnostician    [/bold cyan]")
    console.print("[bold cyan]========================================[/bold cyan]\n")

    # 1. System Platform & Python
    console.print("[bold]1. Python & System Platform[/bold]")
    console.print(f"  Python Version: {sys.version}")
    console.print(f"  Platform: {platform.platform()}")
    console.print(f"  Architecture: {platform.machine()}")
    console.print()

    # 2. SQLite FTS5 Check
    console.print("[bold]2. Database Engines[/bold]")
    db_path = settings.db_path
    console.print(f"  Database Path: {db_path}")
    
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE test_fts USING fts5(content);")
        conn.close()
        console.print("  SQLite FTS5 Extension: [green]Available[/green]")
    except Exception as e:
        console.print(f"  SQLite FTS5 Extension: [red]NOT Available[/red] ({e})")

    # Check local db
    db_exists = db_path.exists()
    if db_exists:
        try:
            storage = Storage(db_path)
            console.print("  Database File: [green]Exists & Readable[/green]")
            console.print(f"    Papers: {storage.count_papers()}")
            console.print(f"    Claims: {storage.count_claims()}")
            console.print(f"    Links: {storage.count_links()}")
            
            # Safely check if paper_chunks table exists and count
            try:
                chunk_count = storage.conn.execute('SELECT count(*) FROM paper_chunks').fetchone()[0]
                console.print(f"    Layout Chunks: {chunk_count}")
            except Exception:
                console.print("    Layout Chunks: 0 (table not initialized)")
            storage.close()
        except Exception as e:
            console.print(f"  Database File: [red]Error reading database[/red] ({e})")
    else:
        console.print("  Database File: [yellow]Not initialized yet[/yellow] (Run 'knowcran init')")
    console.print()

    # 3. PDF Ingestion & Parsers
    console.print("[bold]3. PDF Ingestion & Parsers[/bold]")
    console.print(f"  PDF Directory: {settings.pdf_dir}")
    console.print(f"  Configured Parser strategy: {settings.pdf_parser}")
    
    # Check PyMuPDF
    try:
        import pymupdf
        console.print(f"  PyMuPDF (fitz): [green]Installed[/green] (version {pymupdf.__version__})")
    except ImportError:
        console.print("  PyMuPDF (fitz): [red]NOT Installed[/red] (Install using pip install pymupdf)")

    # Check MinerU API
    mineru_url = settings.mineru_api_url
    console.print(f"  MinerU API Endpoint: {mineru_url}")
    if live:
        import httpx
        try:
            httpx.get(mineru_url, timeout=1.5)
            console.print("    MinerU API Health: [green]Online & Responsive[/green]")
        except Exception as e:
            console.print(f"    MinerU API Health: [yellow]Offline or Unresponsive[/yellow] ({e})")
    else:
        console.print("    MinerU API Health: [dim]Skipped (run with --live to probe)[/dim]")
    console.print()

    # 4. Dense Embeddings
    console.print("[bold]4. Dense Embeddings & Vector Search[/bold]")
    console.print(f"  Embedding Provider: {settings.embedding_provider}")
    console.print(f"  Embedding Model: {settings.embedding_model}")
    console.print(f"  Embedding API Base: {settings.openai_api_base}")
    has_key = bool(settings.openai_api_key)
    key_status = "[green]Configured[/green]" if has_key else "[red]Missing (Embeddings & vector search will be disabled)[/red]"
    console.print(f"  OpenAI API Key: {key_status}")
    if live and has_key and settings.embedding_provider == "openai":
        from knowcran.embeddings import EmbeddingProvider
        try:
            prov = EmbeddingProvider(settings)
            vecs = prov.embed_texts(["healthcheck"])
            if vecs and any(vecs[0]):
                console.print(f"    OpenAI Embeddings Test: [green]Success[/green] (Vector dimension: {len(vecs[0])})")
            else:
                console.print("    OpenAI Embeddings Test: [red]Failed (returned empty/zero vector)[/red]")
        except Exception as e:
            console.print(f"    OpenAI Embeddings Test: [red]Failed[/red] ({e})")
    elif live:
        console.print("    OpenAI Embeddings Test: [dim]Skipped (no key or provider set to none)[/dim]")
    else:
        console.print("    OpenAI Embeddings Test: [dim]Skipped (run with --live to probe)[/dim]")
    console.print()

    # 5. LLM & Agent Providers
    console.print("[bold]5. LLM & Agent Providers[/bold]")
    console.print(f"  LLM Provider: {settings.llm_provider}")
    if settings.llm_provider == "claw":
        console.print(f"  Claw Binary: {settings.claw_bin}")
        if settings.claw_bin:
            exists = Path(settings.claw_bin).exists()
            status = "[green]Exists[/green]" if exists else "[red]NOT Found[/red]"
            console.print(f"    Binary Status: {status}")
        else:
            console.print("    Binary Status: [red]No claw binary path configured[/red]")
    console.print()

    # 6. PDF Downloader Engines
    console.print("[bold]6. PDF Downloader Engines[/bold]")
    console.print(f"  Sci-Hub Fallback Enabled: {settings.scihub_enabled}")
    console.print(f"  LibGen Fallback Enabled: {settings.libgen_enabled}")
    if live:
        import httpx
        # Check internet / Semantic scholar API connectivity
        try:
            httpx.get("https://api.semanticscholar.org", timeout=2.0)
            console.print("  Internet & Semantic Scholar API: [green]Connected[/green]")
        except Exception as e:
            console.print(f"  Internet & Semantic Scholar API: [red]Offline / Unreachable[/red] ({e})")
    else:
        console.print("  Internet connectivity probe: [dim]Skipped (run with --live to probe)[/dim]")
    console.print()


@app.command("pdf-doctor")
def pdf_doctor_cmd(
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
    live: bool = typer.Option(False, "--live", help="Run a live health check on remote services"),
) -> None:
    """Diagnose the local environment, dependencies, database, and configurations (doctor alias)."""
    doctor_cmd(data_dir=data_dir, live=live)


agents_app = typer.Typer(name="agents", help="Manage agent providers.")
app.add_typer(agents_app, name="agents")


@agents_app.command("list")
def agents_list():
    """List available agent providers."""
    from knowcran.agents.registry import get_registry
    registry = get_registry()
    providers = registry.list_providers()
    table = Table(title="Agent Providers")
    table.add_column("Name", style="bold")
    table.add_column("Available")
    table.add_column("Default")
    table.add_column("Capabilities")
    for p in providers:
        avail = "[green]Yes[/green]" if p["available"] else "[red]No[/red]"
        default = "[bold]Yes[/bold]" if p["is_default"] else ""
        caps = ", ".join(p["capabilities"])
        table.add_row(p["name"], avail, default, caps)
    console.print(table)


@agents_app.command("doctor")
def agents_doctor(
    live: bool = typer.Option(False, "--live", help="Run a live test"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
):
    """Check agent provider configuration."""
    from knowcran.agents.registry import get_registry
    from knowcran.agents.schemas import AgentTask

    registry = get_registry()
    providers = registry.list_providers()

    console.print(f"[bold]Default provider:[/bold] {registry.default_name or 'none'}")
    console.print()

    for p in providers:
        status = "[green]Available[/green]" if p["available"] else "[red]Not available[/red]"
        console.print(f"[bold]{p['name']}[/bold]: {status}")
        console.print(f"  Capabilities: {', '.join(p['capabilities'])}")

    if live:
        console.print("\n[bold]Running live health check...[/bold]")
        provider = registry.get()
        task = AgentTask(task_id="health-check", task_type="health_check")
        result = provider.run(task)
        if result.status == "ok":
            console.print(f"[green]Health check passed via {provider.name}[/green]")
        else:
            console.print(f"[red]Health check failed: {result.error}[/red]")


@agents_app.command("failures")
def agents_failures(
    limit: int = typer.Option(20, help="Max failures to show"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
):
    """Show recent agent run failures."""
    settings = _settings(data_dir, None)
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    try:
        failures = storage.get_agent_run_failures(limit=limit)
        if not failures:
            console.print("[green]No recent failures.[/green]")
            return
        table = Table(title="Recent Agent Run Failures")
        table.add_column("Task ID")
        table.add_column("Provider")
        table.add_column("Task Type")
        table.add_column("Error")
        table.add_column("Time")
        for f in failures:
            table.add_row(f["task_id"], f["provider"], f["task_type"], (f.get("error") or "")[:60], f["created_at"][:19])
        console.print(table)
    finally:
        storage.close()


topics_app = typer.Typer(name="topics", help="Manage topics and aliases.")
app.add_typer(topics_app, name="topics")


@topics_app.command("alias")
def topics_alias(
    alias: str = typer.Argument(help="Alias name"),
    canonical: str = typer.Argument(help="Canonical topic name"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
):
    """Add a topic alias mapping."""
    settings = _settings(data_dir, None)
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    try:
        storage.add_topic_alias(alias, canonical)
        console.print(f"[green]Added alias: '{alias}' -> '{canonical}'[/green]")
    finally:
        storage.close()


@topics_app.command("coverage")
def topics_coverage(
    topic: str = typer.Argument(help="Topic to check coverage for"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
):
    """Show discovery coverage for a topic."""
    settings = _settings(data_dir, None)
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    try:
        canonical = storage.resolve_topic(topic)
        coverage = storage.get_discovery_topic_coverage(canonical)
        paper_count = len(storage.get_topic_papers(canonical, limit=10000))

        console.print(f"[bold]Topic:[/bold] {topic}")
        if canonical != topic:
            console.print(f"[bold]Canonical:[/bold] {canonical}")
        console.print(f"[bold]Papers in DB:[/bold] {paper_count}")
        console.print(f"[bold]Discovery queries:[/bold] {coverage.get('total_queries', 0)}")

        by_status = coverage.get("by_status", {})
        for status, info in by_status.items():
            console.print(f"  {status}: {info['count']} queries, {info['papers']} papers")

        # Show aliases
        aliases = storage.get_topic_aliases(canonical)
        if aliases:
            console.print(f"[bold]Aliases:[/bold] {', '.join(aliases)}")
    finally:
        storage.close()


@topics_app.command("list")
def topics_list(
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
):
    """List all known topics."""
    settings = _settings(data_dir, None)
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    try:
        topics = storage.get_canonical_topics()
        if not topics:
            console.print("[yellow]No topics found. Run 'discover' first.[/yellow]")
            return
        table = Table(title="Topics")
        table.add_column("Topic", style="bold")
        table.add_column("Papers")
        table.add_column("Aliases")
        for t in topics:
            paper_count = len(storage.get_topic_papers(t, limit=10000))
            aliases = storage.get_topic_aliases(t)
            table.add_row(t, str(paper_count), ", ".join(aliases) if aliases else "")
        console.print(table)
    finally:
        storage.close()


@app.command("run-topic")
def run_topic_cmd(
    topic: str = typer.Argument(help="Topic for the full pipeline run"),
    limit: int = typer.Option(50, help="Max papers to process"),
    strategy: str = typer.Option("fastest", help="Download strategy: fastest, oa_first, legal_only, scihub_only"),
    fulltext: bool = typer.Option(True, "--fulltext/--abstract-only", help="Use full-text extraction when available"),
    skip_discover: bool = typer.Option(False, "--skip-discover", help="Skip paper discovery step"),
    skip_download: bool = typer.Option(False, "--skip-download", help="Skip PDF download step"),
    skip_parse: bool = typer.Option(False, "--skip-parse", help="Skip PDF parse step"),
    skip_review: bool = typer.Option(False, "--skip-review", help="Skip review generation step"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
    vault_dir: str | None = typer.Option(None, "--vault-dir", help="Vault directory path"),
) -> None:
    """Run the full pipeline: discover -> download -> parse -> extract -> notes -> review.

    Produces a structured output directory with run manifest, paper inventory,
    evidence matrix, literature review, and bibliography.
    """
    settings = _settings(data_dir, vault_dir)
    from knowcran.workflow import run_topic_workflow

    console.print(f"[bold]Starting pipeline for topic: {topic}[/bold]")
    result = run_topic_workflow(
        topic=topic,
        limit=limit,
        strategy=strategy,
        settings=settings,
        skip_discover=skip_discover,
        skip_download=skip_download,
        skip_parse=skip_parse,
        skip_review=skip_review,
        fulltext=fulltext,
    )

    if result["status"] == "completed":
        console.print(f"[green]Pipeline complete![/green]")
        console.print(f"  Run ID: {result['run_id']}")
        console.print(f"  Output: {result['output_dir']}")
        steps = result.get("steps", {})
        if "discover" in steps:
            console.print(f"  Papers discovered: {steps['discover'].get('count', 0)}")
        if "download" in steps and isinstance(steps["download"], dict):
            console.print(f"  PDFs downloaded: {steps['download'].get('downloaded', 0)}")
        if "parse" in steps and isinstance(steps["parse"], dict):
            console.print(f"  PDFs parsed: {steps['parse'].get('parsed', 0)}")
        if "extract" in steps:
            console.print(f"  Claims extracted: {steps['extract'].get('total', 0)}")
            console.print(f"    Full-text: {steps['extract'].get('fulltext', 0)}")
            console.print(f"    Abstract-only: {steps['extract'].get('abstract_only', 0)}")
        if "review" in steps and isinstance(steps["review"], dict):
            console.print(f"  Review: {steps['review'].get('evidence_count', 0)} evidence items")
    else:
        console.print(f"[red]Pipeline failed: {result.get('error', 'Unknown error')}[/red]")


@app.command("serve-mcp")
def serve_mcp_cmd() -> None:
    """Start MCP server with all tools (read + write + audit). Backward compat alias."""
    from knowcran.server.mcp import serve_mcp
    serve_mcp()


@app.command("serve-mcp-readonly")
def serve_mcp_readonly_cmd() -> None:
    """Start read-only MCP server (safe for long-running connections). No network, no writes."""
    from knowcran.server.mcp import serve_mcp_readonly
    serve_mcp_readonly()


@app.command("serve-mcp-curate")
def serve_mcp_curate_cmd() -> None:
    """Start curate MCP server (all tools including discover/review/export). Requires approval."""
    from knowcran.server.mcp import serve_mcp_curate
    serve_mcp_curate()


@app.command("serve-mcp-admin")
def serve_mcp_admin_cmd() -> None:
    """Start admin MCP server (local human maintenance only)."""
    from knowcran.server.mcp import serve_mcp_admin
    serve_mcp_admin()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
