"""Main CLI application."""

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from anki_gen.cache.manager import CacheManager
from anki_gen.commands.parse import execute_parse
from anki_gen.core.parser_factory import ParserFactory
from anki_gen.models.extraction import ExtractionMethod

app = typer.Typer(
    name="anki-gen",
    help="Parse EPUB/PDF files into AI-readable format for flashcard generation.",
    add_completion=False,
)

console = Console()

# Cache subcommand group
cache_app = typer.Typer(help="Cache management commands")
app.add_typer(cache_app, name="cache")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Parse EPUB/PDF files into AI-readable format for flashcard generation.

    Run without arguments to start the interactive wizard.
    """
    if ctx.invoked_subcommand is None:
        # No subcommand provided, run the interactive wizard
        from anki_gen.commands.run import execute_run

        execute_run(
            book_path=None,
            non_interactive=False,
            force=False,
            console=console,
        )


@app.command()
def run(
    book_path: Annotated[
        Optional[Path],
        typer.Argument(
            help="Path to book file (PDF/EPUB). If omitted, shows file picker.",
        ),
    ] = None,
    non_interactive: Annotated[
        bool,
        typer.Option(
            "--yes", "-y",
            help="Skip confirmations, use all defaults",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force", "-f",
            help="Force regenerate all sections (ignore already-generated)",
        ),
    ] = False,
) -> None:
    """Interactive wizard to parse, generate, and export flashcards.

    Guides you through the complete flashcard generation workflow with
    file selection, section picking, and configuration options.
    """
    # Validate book_path if provided
    if book_path is not None:
        if not book_path.exists():
            console.print(f"[red]File not found: {book_path}[/]")
            raise typer.Exit(1)
        if not ParserFactory.is_supported(book_path):
            console.print(f"[red]Unsupported file format: {book_path.suffix}[/]")
            console.print("[dim]Supported formats: .epub, .pdf[/]")
            raise typer.Exit(1)
        book_path = book_path.resolve()

    # Check for non-interactive mode without book path
    if non_interactive and book_path is None:
        console.print("[red]Error: --yes requires a book path argument[/]")
        console.print("[dim]Example: anki-gen run book.pdf --yes[/]")
        raise typer.Exit(1)

    try:
        from anki_gen.commands.run import execute_run

        execute_run(
            book_path=book_path,
            non_interactive=non_interactive,
            force=force,
            console=console,
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command()
def parse(
    book_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the book file (EPUB or PDF)",
            exists=True,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    sections: Annotated[
        Optional[str],
        typer.Option(
            "--sections",
            "-s",
            help="Sections to extract by index: '1,3,5-7' or 'all' (use 'anki-gen info' to see indices)",
        ),
    ] = None,
    interactive: Annotated[
        bool,
        typer.Option(
            "--interactive",
            "-i",
            help="Interactive mode: display TOC and select sections",
        ),
    ] = False,
    output_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--output-dir",
            "-o",
            help="Output directory (default: {book_name}_chapters/)",
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
    by_page: Annotated[
        Optional[int],
        typer.Option(
            "--by-page",
            help="Force page-based chunking with N pages per section (PDF only, default: 10)",
            min=1,
        ),
    ] = None,
) -> None:
    """Parse an EPUB or PDF file and extract sections."""
    # Validate file format
    if not ParserFactory.is_supported(book_path):
        console.print(f"[red]Unsupported file format: {book_path.suffix}[/]")
        console.print("[dim]Supported formats: .epub, .pdf[/]")
        raise typer.Exit(1)

    if output_format not in ("markdown", "text", "html"):
        console.print(
            f"[red]Invalid format: {output_format}. Use markdown, text, or html.[/]"
        )
        raise typer.Exit(1)

    try:
        execute_parse(
            book_path=book_path,
            chapters=sections,  # internally still uses 'chapters' param name
            interactive=interactive,
            output_dir=output_dir,
            output_format=output_format,  # type: ignore
            force=force,
            quiet=quiet,
            console=console,
            by_page=by_page,
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command()
def info(
    book_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the book file (EPUB or PDF)",
            exists=True,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
) -> None:
    """Display book metadata and table of contents."""
    # Validate file format
    if not ParserFactory.is_supported(book_path):
        console.print(f"[red]Unsupported file format: {book_path.suffix}[/]")
        console.print("[dim]Supported formats: .epub, .pdf[/]")
        raise typer.Exit(1)

    try:
        parser = ParserFactory.create(book_path)
        parsed = parser.parse()

        # Build book info panel
        info_lines = [
            f"[bold]{parsed.metadata.title}[/]",
            "",
            f"[dim]Author(s):[/] {', '.join(parsed.metadata.authors) or 'Unknown'}",
            f"[dim]Format:[/] {parsed.source_format.upper()}",
        ]

        # Add language/publisher for EPUB
        if parsed.source_format == "epub":
            info_lines.append(
                f"[dim]Language:[/] {parsed.metadata.language or 'Unknown'}"
            )
            info_lines.append(
                f"[dim]Publisher:[/] {parsed.metadata.publisher or 'Unknown'}"
            )

        info_lines.append(f"[dim]Total Sections:[/] {len(parsed.chapters)}")

        # Add extraction info for PDF
        if parsed.source_format == "pdf":
            method_display = parsed.extraction_method.value.replace("_", " ").title()
            info_lines.append(
                f"[dim]Detection:[/] {method_display} "
                f"(confidence: {parsed.extraction_confidence:.0%})"
            )

        # Show warnings if any
        if parsed.warnings:
            info_lines.append("")
            for warning in parsed.warnings:
                info_lines.append(f"[yellow]⚠ {warning}[/]")

        # Add tip about --by-page customization for page-based chunking
        if (
            parsed.source_format == "pdf"
            and parsed.extraction_method == ExtractionMethod.PDF_PAGE_CHUNKS
        ):
            info_lines.append("")
            info_lines.append(
                "[cyan]💡 Tip: Use --by-page N with 'parse' to adjust pages per section "
                "(e.g., --by-page 5 for smaller sections)[/]"
            )

        console.print()
        console.print(
            Panel(
                "\n".join(info_lines),
                title="Book Information",
                border_style="green",
            )
        )

        # TOC table
        console.print()
        table = Table(
            title="Table of Contents", show_header=True, header_style="bold cyan"
        )
        table.add_column("#", style="dim", width=4)
        table.add_column("Title", style="white")
        table.add_column("Words", justify="right", style="green")

        # Add pages column for PDF
        if parsed.source_format == "pdf":
            table.add_column("Pages", justify="right", style="dim")

        for chapter in parsed.chapters:
            # Add indentation only for PDF outline (true hierarchy)
            if (
                parsed.source_format == "pdf"
                and parsed.extraction_method.value == "pdf_outline"
                and chapter.level > 0
            ):
                indent = "  " * chapter.level
                display_title = f"{indent}{chapter.title}"
            else:
                display_title = chapter.title

            row = [
                str(chapter.index + 1),
                display_title,
                f"{chapter.word_count:,}",
            ]
            if parsed.source_format == "pdf":
                if chapter.page_start is not None and chapter.page_end is not None:
                    row.append(f"{chapter.page_start + 1}-{chapter.page_end + 1}")
                else:
                    row.append("—")
            table.add_row(*row)

        console.print(table)
        console.print()

    except Exception as e:
        console.print(f"[red]Error reading file: {e}[/]")
        raise typer.Exit(1)


@app.command()
def generate(
    chapters_dir: Annotated[
        Path,
        typer.Argument(
            help="Path to directory containing parsed section JSON files",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ],
    sections: Annotated[
        Optional[str],
        typer.Option(
            "--sections",
            "-s",
            help="Sections to generate by index: '1,3,5-7' or 'all' (default: all)",
        ),
    ] = None,
    max_cards: Annotated[
        Optional[int],
        typer.Option(
            "--max-cards",
            "-n",
            help="Maximum total cards per section (default: AI decides)",
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
    ] = "gemini-3-pro-preview",
    deck: Annotated[
        Optional[str],
        typer.Option(
            "--deck",
            "-d",
            help="Override deck name (default: auto-generated from book/chapter)",
        ),
    ] = None,
    tags: Annotated[
        Optional[list[str]],
        typer.Option(
            "--tag",
            "-t",
            help="Add extra global tags (can be used multiple times)",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show what would be generated without calling AI",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Regenerate all sections, even if already generated",
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
    """Generate AI-powered flashcards from parsed sections.

    Outputs a single combined file per section (chapter_XXX_cards.txt) containing
    both Basic and Cloze cards with Anki import headers for automatic deck placement,
    tags, and GUID support.
    """
    try:
        from anki_gen.commands.generate import execute_generate

        execute_generate(
            chapters_dir=chapters_dir,
            max_cards=max_cards,
            model=model,
            dry_run=dry_run,
            quiet=quiet,
            console=console,
            chapters=sections,  # internally still uses 'chapters' param name
            deck=deck,
            tags=tags,
            force=force,
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command()
def export(
    chapters_dir: Annotated[
        Path,
        typer.Argument(
            help="Path to directory containing generated card files",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ],
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Output file path (default: {chapters_dir}/all_cards.txt)",
        ),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Suppress progress output",
        ),
    ] = False,
) -> None:
    """Export all section cards into a single Anki-importable file.

    Combines multiple chapter_XXX_cards.txt files into one file while preserving
    per-section deck hierarchy. Displays statistics summary after export.
    """
    try:
        from anki_gen.commands.export import execute_export

        execute_export(
            chapters_dir=chapters_dir,
            output_file=output,
            console=console,
            quiet=quiet,
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command()
def status(
    chapters_dir: Annotated[
        Path,
        typer.Argument(
            help="Path to directory containing parsed section files",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ],
) -> None:
    """Show status summary of parsed, generated, and exported sections.

    Displays a comprehensive overview of what anki-gen has done for a book,
    including which sections have been parsed, which have flashcards generated,
    card counts, and export status.
    """
    try:
        from anki_gen.commands.status import execute_status

        execute_status(
            chapters_dir=chapters_dir,
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
    """Clear all cached data."""
    cache_manager = CacheManager(project_dir.resolve())
    count = cache_manager.clear_cache()

    if count > 0:
        console.print(f"[green]Cleared {count} cached file(s)[/]")
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
    """List all cached files."""
    cache_manager = CacheManager(project_dir.resolve())
    cached = cache_manager.list_cached()

    if not cached:
        console.print("[dim]No cached files[/]")
        return

    table = Table(title="Cached Files", show_header=True, header_style="bold cyan")
    table.add_column("Path", style="white")
    table.add_column("Hash", style="dim", width=12)

    for path, file_hash in cached:
        # Truncate path for display
        display_path = path if len(path) < 60 else "..." + path[-57:]
        table.add_row(display_path, file_hash[:12])

    console.print(table)


if __name__ == "__main__":
    app()
