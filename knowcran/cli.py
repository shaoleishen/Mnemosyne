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
) -> None:
    """Search Semantic Scholar and store papers."""
    settings = _settings(data_dir, vault_dir)
    from knowcran.discovery import discover as do_discover
    from knowcran.semantic_scholar import SemanticScholarClient
    from knowcran.storage import Storage
    client = SemanticScholarClient(api_key=settings.s2_api_key, rate_limit=settings.rate_limit_seconds, raw_dir=settings.raw_dir)
    storage = Storage(db_path=settings.db_path)
    papers = do_discover(question, limit=limit, expand=expand, client=client, storage=storage)
    console.print(f"[green]Discovered {len(papers)} papers.[/green]")


@app.command("read-paper")
def read_paper_cmd(
    paper_id: str = typer.Argument(help="Semantic Scholar paper ID"),
    topic: str | None = typer.Option(None, help="Topic to tag claims with (for review compatibility)"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
) -> None:
    """Extract claims from a single paper's abstract."""
    settings = _settings(data_dir, None)
    from knowcran.reading import read_paper
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    claims = read_paper(paper_id, topic=topic, storage=storage)
    if not claims:
        console.print("[yellow]Paper not found in database.[/yellow]")
        return
    for c in claims:
        console.print(f"[bold]{c.evidence_type}[/bold] (conf {c.confidence}): {c.claim_text[:120]}")


@app.command("read-topic")
def read_topic_cmd(
    topic: str = typer.Argument(help="Topic to read"),
    limit: int = typer.Option(20, help="Max papers to process"),
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
) -> None:
    """Extract claims from all papers matching a topic."""
    settings = _settings(data_dir, None)
    from knowcran.reading import read_topic
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    claims = read_topic(topic, limit=limit, storage=storage)
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
    data_dir: str | None = typer.Option(None, "--data-dir", help="Data directory path"),
    vault_dir: str | None = typer.Option(None, "--vault-dir", help="Vault directory path"),
) -> None:
    """Generate a literature review from stored claims."""
    settings = _settings(data_dir, vault_dir)
    from knowcran.review import review as do_review
    from knowcran.storage import Storage
    storage = Storage(db_path=settings.db_path)
    output = do_review(topic, max_papers=max_papers, storage=storage, vault_dir=settings.vault_dir)
    console.print(f"[green]Review generated with {len(output.evidence_matrix)} evidence items and {len(output.paper_ids)} papers.[/green]")


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
        console.print(f"Links:   {storage.count_links()}")
    finally:
        storage.close()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
