"""Parse command implementation."""

import re
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table

from anki_gen.cache.manager import CacheManager
from anki_gen.cache.models import CachedBookStructure
from anki_gen.core.output_writer import OutputWriter
from anki_gen.core.parser_factory import ParserFactory
from anki_gen.models.book import ParsedBook, TOCEntry
from anki_gen.models.extraction import ExtractionMethod


def parse_chapter_selection(selection: str, total_chapters: int) -> list[int]:
    """Parse user chapter selection string to list of indices.

    Supports: "1,3,5-7", "all", "1-10", etc.
    Returns 0-based indices.
    """
    selection = selection.strip().lower()

    if selection == "all":
        return list(range(total_chapters))

    indices = set()
    for part in selection.split(","):
        part = part.strip()
        if not part:
            continue

        if "-" in part:
            match = re.match(r"(\d+)\s*-\s*(\d+)", part)
            if match:
                start, end = int(match.group(1)), int(match.group(2))
                indices.update(range(start - 1, end))  # Convert to 0-based
        else:
            try:
                indices.add(int(part) - 1)  # Convert to 0-based
            except ValueError:
                continue

    # Filter valid indices
    return sorted(i for i in indices if 0 <= i < total_chapters)


def display_toc(
    toc: list[TOCEntry],
    chapters: list,
    console: Console,
) -> None:
    """Display table of contents."""
    table = Table(title="Table of Contents", show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="white")
    table.add_column("Words", justify="right", style="green")

    for i, chapter in enumerate(chapters):
        table.add_row(str(i + 1), chapter.title, f"{chapter.word_count:,}")

    console.print(table)


def interactive_select(
    chapters: list,
    console: Console,
) -> list[int]:
    """Interactively select chapters."""
    console.print()
    console.print(
        Panel(
            "[bold]Select sections to extract:[/]\n"
            "  - Enter section numbers (e.g., [cyan]1,3,5-7[/])\n"
            "  - Enter [cyan]all[/] for all sections\n"
            "  - Enter [cyan]q[/] to quit",
            title="Selection",
            border_style="blue",
        )
    )
    console.print()

    while True:
        selection = Prompt.ask("Your selection")

        if selection.lower() == "q":
            return []

        indices = parse_chapter_selection(selection, len(chapters))

        if indices:
            console.print(f"\n[green]Selected {len(indices)} section(s)[/]")
            return indices
        else:
            console.print("[red]Invalid selection. Please try again.[/]")


def get_default_output_dir(book_path: Path) -> Path:
    """Get default output directory based on book filename."""
    stem = book_path.stem
    # Clean up the filename for directory name
    clean_stem = re.sub(r"[^\w\s-]", "", stem).strip()
    clean_stem = re.sub(r"[-\s]+", "_", clean_stem)
    return book_path.parent / f"{clean_stem}_chapters"


def execute_parse(
    book_path: Path,
    chapters: str | None,
    interactive: bool,
    output_dir: Path | None,
    output_format: Literal["markdown", "text", "html"],
    force: bool,
    quiet: bool,
    console: Console,
    by_page: int | None = None,
) -> None:
    """Execute the parse command."""
    # Detect format
    file_format = ParserFactory.detect_format(book_path)
    if file_format == "unknown":
        console.print(f"[red]Unsupported file format: {book_path.suffix}[/]")
        console.print("[dim]Supported formats: .epub, .pdf[/]")
        return

    # Determine cache directory (use book's parent directory)
    cache_manager = CacheManager(book_path.parent)

    parsed: ParsedBook | None = None
    cached: CachedBookStructure | None = None

    # Check cache first
    if not force:
        cached = cache_manager.get_cached_structure(book_path)
        if cached and not quiet:
            console.print("[dim]Using cached structure[/]")

    # Parse if not cached
    if cached is None:
        format_name = file_format.upper()
        if not quiet:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(f"Parsing {format_name}...", total=None)
                parser = ParserFactory.create(book_path, pages_per_chunk=by_page)
                parsed = parser.parse()
        else:
            parser = ParserFactory.create(book_path, pages_per_chunk=by_page)
            parsed = parser.parse()

        # Save to cache
        cache_manager.save_structure(book_path, parsed)
        if not quiet:
            console.print("[dim]Cached structure[/]")
    else:
        # Reconstruct from cache - re-parse to get raw content
        parser = ParserFactory.create(book_path, pages_per_chunk=by_page)
        parsed = parser.parse()

    # Display book info
    if not quiet:
        console.print()

        # Build info panel content
        info_lines = [
            f"[bold]{parsed.metadata.title}[/]",
            f"[dim]Author(s):[/] {', '.join(parsed.metadata.authors) or 'Unknown'}",
            f"[dim]Sections:[/] {len(parsed.chapters)}",
            f"[dim]Format:[/] {parsed.source_format.upper()}",
        ]

        # Add extraction method for PDF
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
                "[cyan]💡 Tip: Use --by-page N to adjust pages per section "
                "(e.g., --by-page 5 for smaller sections)[/]"
            )

        console.print(
            Panel(
                "\n".join(info_lines),
                title="Book Info",
                border_style="green",
            )
        )
        console.print()

    # Determine which chapters to extract
    if interactive or chapters is None:
        # Show TOC and prompt for selection
        if not quiet:
            display_toc(parsed.toc, parsed.chapters, console)
        selected_indices = interactive_select(parsed.chapters, console)
    else:
        selected_indices = parse_chapter_selection(chapters, len(parsed.chapters))

    if not selected_indices:
        console.print("[yellow]No sections selected. Exiting.[/]")
        return

    # Determine output directory
    final_output_dir = output_dir or get_default_output_dir(book_path)

    # Write chapters
    writer = OutputWriter(final_output_dir, book_path)
    chapter_metadata = []

    if not quiet:
        console.print()
        with Progress(console=console) as progress:
            task = progress.add_task(
                "Extracting sections...", total=len(selected_indices)
            )

            for idx in selected_indices:
                chapter = parsed.chapters[idx]
                _, metadata = writer.write_chapter(chapter, output_format)
                chapter_metadata.append(metadata)
                progress.update(
                    task, advance=1, description=f"Extracting: {chapter.title[:40]}..."
                )
    else:
        for idx in selected_indices:
            chapter = parsed.chapters[idx]
            _, metadata = writer.write_chapter(chapter, output_format)
            chapter_metadata.append(metadata)

    # Write manifest
    manifest_path = writer.write_manifest(parsed, selected_indices, chapter_metadata)

    # Summary
    if not quiet:
        console.print()

        summary_lines = [
            f"[green]Successfully extracted {len(selected_indices)} section(s)[/]",
            "",
            f"[dim]Output directory:[/] {final_output_dir}",
            f"[dim]Manifest:[/] {manifest_path.name}",
        ]

        # Add extraction info for PDF
        if parsed.source_format == "pdf":
            method_display = parsed.extraction_method.value.replace("_", " ").title()
            summary_lines.append(f"[dim]Extraction method:[/] {method_display}")
            summary_lines.append(
                f"[dim]Average confidence:[/] {parsed.extraction_confidence:.0%}"
            )

        console.print(
            Panel(
                "\n".join(summary_lines),
                title="Complete",
                border_style="green",
            )
        )
