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


@app.command()
def init() -> None:
    """Initialize data directories and database."""
    from knowcran.config import DATA_DIR, VAULT_DIR, RAW_DIR
    for d in [DATA_DIR, RAW_DIR, VAULT_DIR / "papers", VAULT_DIR / "claims", VAULT_DIR / "topics", VAULT_DIR / "reviews"]:
        d.mkdir(parents=True, exist_ok=True)
    from knowcran.storage import Storage
    Storage()
    console.print("[green]KnowCran initialized.[/green]")


@app.command()
def discover(
    question: str = typer.Argument(help="Disease or research question"),
    limit: int = typer.Option(100, help="Max papers per query"),
    expand: bool = typer.Option(False, help="Expand via references/citations/recommendations"),
) -> None:
    """Search Semantic Scholar and store papers."""
    from knowcran.discovery import discover as do_discover
    papers = do_discover(question, limit=limit, expand=expand)
    console.print(f"[green]Discovered {len(papers)} papers.[/green]")


@app.command("read-paper")
def read_paper_cmd(
    paper_id: str = typer.Argument(help="Semantic Scholar paper ID"),
) -> None:
    """Extract claims from a single paper's abstract."""
    from knowcran.reading import read_paper
    claims = read_paper(paper_id)
    if not claims:
        console.print("[yellow]Paper not found in database.[/yellow]")
        return
    for c in claims:
        console.print(f"[bold]{c.evidence_type}[/bold] (conf {c.confidence}): {c.claim_text[:120]}")


@app.command("read-topic")
def read_topic_cmd(
    topic: str = typer.Argument(help="Topic to read"),
    limit: int = typer.Option(20, help="Max papers to process"),
) -> None:
    """Extract claims from all papers matching a topic."""
    from knowcran.reading import read_topic
    claims = read_topic(topic, limit=limit)
    console.print(f"[green]Extracted {len(claims)} claims from topic papers.[/green]")


@app.command("export-obsidian")
def export_obsidian_cmd(
    topic: str = typer.Argument(help="Topic to export"),
) -> None:
    """Export Obsidian vault notes for a topic."""
    from knowcran.obsidian import export_obsidian
    counts = export_obsidian(topic)
    console.print(f"[green]Exported: {counts['papers']} papers, {counts['claims']} claims, {counts['topics']} topic notes.[/green]")


@app.command()
def review(
    topic: str = typer.Argument(help="Topic to review"),
    max_papers: int = typer.Option(20, help="Max papers for review"),
) -> None:
    """Generate a literature review from stored claims."""
    from knowcran.review import review as do_review
    output = do_review(topic, max_papers=max_papers)
    console.print(f"[green]Review generated with {len(output.evidence_matrix)} evidence items and {len(output.paper_ids)} papers.[/green]")


@app.command("show-paper")
def show_paper_cmd(
    paper_id: str = typer.Argument(help="Paper ID to display"),
) -> None:
    """Display paper details from the database."""
    from knowcran.storage import Storage
    storage = Storage()
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
def stats() -> None:
    """Show database statistics."""
    from knowcran.storage import Storage
    storage = Storage()
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
