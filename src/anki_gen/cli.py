"""Main CLI application."""

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from anki_gen.cache.manager import CacheManager
from anki_gen.commands.parse import execute_parse
from anki_gen.core.epub_parser import EpubParser

app = typer.Typer(
    name="anki-gen",
    help="Parse EPUB files into AI-readable format for flashcard generation.",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()

# Cache subcommand group
cache_app = typer.Typer(help="Cache management commands")
app.add_typer(cache_app, name="cache")


@app.command()
def parse(
    epub_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the EPUB file to parse",
            exists=True,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    chapters: Annotated[
        Optional[str],
        typer.Option(
            "--chapters",
            "-c",
            help="Chapters to extract: '1,3,5-7' or 'all' (default: interactive)",
        ),
    ] = None,
    interactive: Annotated[
        bool,
        typer.Option(
            "--interactive",
            "-i",
            help="Interactive mode: display TOC and select chapters",
        ),
    ] = False,
    output_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--output-dir",
            "-o",
            help="Output directory (default: {epub_name}_chapters/)",
        ),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format: markdown, text, or html",
        ),
    ] = "markdown",
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Force re-parsing, ignore cache",
        ),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Suppress progress output",
        ),
    ] = False,
) -> None:
    """Parse an EPUB file and extract chapters."""
    if output_format not in ("markdown", "text", "html"):
        console.print(f"[red]Invalid format: {output_format}. Use markdown, text, or html.[/]")
        raise typer.Exit(1)

    try:
        execute_parse(
            epub_path=epub_path,
            chapters=chapters,
            interactive=interactive,
            output_dir=output_dir,
            output_format=output_format,  # type: ignore
            force=force,
            quiet=quiet,
            console=console,
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command()
def info(
    epub_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the EPUB file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
) -> None:
    """Display EPUB metadata and table of contents."""
    try:
        parser = EpubParser(epub_path)
        parsed = parser.parse()

        # Book info
        console.print()
        console.print(
            Panel(
                f"[bold]{parsed.metadata.title}[/]\n\n"
                f"[dim]Author(s):[/] {', '.join(parsed.metadata.authors) or 'Unknown'}\n"
                f"[dim]Language:[/] {parsed.metadata.language or 'Unknown'}\n"
                f"[dim]Publisher:[/] {parsed.metadata.publisher or 'Unknown'}\n"
                f"[dim]Total Chapters:[/] {len(parsed.chapters)}",
                title="Book Information",
                border_style="green",
            )
        )

        # TOC table
        console.print()
        table = Table(title="Table of Contents", show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("Title", style="white")
        table.add_column("Words", justify="right", style="green")

        for chapter in parsed.chapters:
            table.add_row(
                str(chapter.index + 1),
                chapter.title,
                f"{chapter.word_count:,}",
            )

        console.print(table)
        console.print()

    except Exception as e:
        console.print(f"[red]Error reading EPUB: {e}[/]")
        raise typer.Exit(1)


@app.command()
def generate(
    chapters_dir: Annotated[
        Path,
        typer.Argument(
            help="Path to directory containing parsed chapter JSON files",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ],
    max_cards: Annotated[
        Optional[int],
        typer.Option(
            "--max-cards",
            "-n",
            help="Maximum cards per chapter (default: AI decides)",
            min=1,
        ),
    ] = None,
    model: Annotated[
        str,
        typer.Option(
            "--model",
            "-m",
            help="Gemini model to use",
        ),
    ] = "gemini-3-pro",
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show what would be generated without calling AI",
        ),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Suppress progress output",
        ),
    ] = False,
) -> None:
    """Generate AI-powered flashcards from parsed chapters using Gemini."""
    try:
        from anki_gen.commands.generate import execute_generate

        execute_generate(
            chapters_dir=chapters_dir,
            max_cards=max_cards,
            model=model,
            dry_run=dry_run,
            quiet=quiet,
            console=console,
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@cache_app.command("clear")
def cache_clear(
    project_dir: Annotated[
        Path,
        typer.Option(
            "--dir",
            "-d",
            help="Project directory containing the cache (default: current directory)",
        ),
    ] = Path("."),
) -> None:
    """Clear all cached EPUB data."""
    cache_manager = CacheManager(project_dir.resolve())
    count = cache_manager.clear_cache()

    if count > 0:
        console.print(f"[green]Cleared {count} cached EPUB(s)[/]")
    else:
        console.print("[dim]No cache to clear[/]")


@cache_app.command("list")
def cache_list(
    project_dir: Annotated[
        Path,
        typer.Option(
            "--dir",
            "-d",
            help="Project directory containing the cache (default: current directory)",
        ),
    ] = Path("."),
) -> None:
    """List all cached EPUBs."""
    cache_manager = CacheManager(project_dir.resolve())
    cached = cache_manager.list_cached()

    if not cached:
        console.print("[dim]No cached EPUBs[/]")
        return

    table = Table(title="Cached EPUBs", show_header=True, header_style="bold cyan")
    table.add_column("Path", style="white")
    table.add_column("Hash", style="dim", width=12)

    for path, file_hash in cached:
        # Truncate path for display
        display_path = path if len(path) < 60 else "..." + path[-57:]
        table.add_row(display_path, file_hash[:12])

    console.print(table)


if __name__ == "__main__":
    app()
