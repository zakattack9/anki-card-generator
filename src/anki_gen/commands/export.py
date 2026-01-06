"""Export command implementation."""

import re
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from anki_gen.models.output import BookOutput


@dataclass
class ChapterCards:
    """Cards from a single chapter file."""

    chapter_num: int
    deck_name: str
    basic_count: int
    cloze_count: int
    card_lines: list[str]  # Raw card lines (without headers)


@dataclass
class ExportStats:
    """Statistics for the export operation."""

    total_chapters: int
    total_cards: int
    total_basic: int
    total_cloze: int
    chapters: list[tuple[int, str, int, int]]  # (num, title, basic, cloze)


def find_card_files(chapters_dir: Path) -> list[Path]:
    """Find all chapter card files in directory."""
    return sorted(chapters_dir.glob("chapter_*_cards.txt"))


def extract_chapter_number(path: Path) -> int:
    """Extract chapter number from filename (chapter_011_cards.txt -> 11)."""
    match = re.search(r"chapter_(\d+)", path.stem)
    if match:
        return int(match.group(1))
    return 0


def parse_card_file(path: Path) -> ChapterCards | None:
    """Parse a chapter cards file and extract deck name and card lines.

    Returns None if the file is invalid or empty.
    """
    content = path.read_text()
    lines = content.strip().split("\n")

    deck_name = ""
    card_lines: list[str] = []
    basic_count = 0
    cloze_count = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Extract deck name from header
        if line.startswith("#deck:"):
            deck_name = line[6:].strip()
            continue

        # Skip other headers
        if line.startswith("#"):
            continue

        # This is a card line
        card_lines.append(line)

        # Count card types
        if line.startswith("Basic|"):
            basic_count += 1
        elif line.startswith("Cloze|"):
            cloze_count += 1

    if not deck_name or not card_lines:
        return None

    return ChapterCards(
        chapter_num=extract_chapter_number(path),
        deck_name=deck_name,
        basic_count=basic_count,
        cloze_count=cloze_count,
        card_lines=card_lines,
    )


def load_manifest(chapters_dir: Path) -> BookOutput | None:
    """Load the manifest.json file from chapters directory."""
    manifest_path = chapters_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    return BookOutput.model_validate_json(manifest_path.read_text())


def build_combined_export(
    chapters: list[ChapterCards],
    book_slug: str,
    global_tags: list[str] | None = None,
) -> str:
    """Build combined export file with per-card deck column.

    Format:
    - Headers with #deck column:6 to specify per-card deck
    - Each card line has deck appended as 6th column
    """
    # Build headers
    tags_str = f"anki-gen {book_slug}"
    if global_tags:
        tags_str += " " + " ".join(global_tags)

    lines = [
        "#separator:Pipe",
        "#html:true",
        f"#tags:{tags_str}",
        "#notetype column:1",
        "#tags column:4",
        "#guid column:5",
        "#deck column:6",
        "#columns:Note Type|Field 1|Field 2|Tags|GUID|Deck",
    ]

    # Add cards from each chapter with deck column
    for chapter in chapters:
        for card_line in chapter.card_lines:
            # Append deck name as 6th column
            lines.append(f"{card_line}|{chapter.deck_name}")

    return "\n".join(lines)


def calculate_stats(chapters: list[ChapterCards]) -> ExportStats:
    """Calculate export statistics."""
    total_basic = sum(c.basic_count for c in chapters)
    total_cloze = sum(c.cloze_count for c in chapters)

    chapter_stats = [
        (c.chapter_num, c.deck_name.split("::")[-1].strip(), c.basic_count, c.cloze_count)
        for c in chapters
    ]

    return ExportStats(
        total_chapters=len(chapters),
        total_cards=total_basic + total_cloze,
        total_basic=total_basic,
        total_cloze=total_cloze,
        chapters=chapter_stats,
    )


def display_stats(stats: ExportStats, output_path: Path, console: Console) -> None:
    """Display export statistics."""
    # Summary panel
    console.print()
    console.print(
        Panel(
            f"[green]Exported {stats.total_cards} cards from {stats.total_chapters} section(s)[/]\n\n"
            f"[dim]Basic cards:[/] {stats.total_basic}\n"
            f"[dim]Cloze cards:[/] {stats.total_cloze}\n"
            f"[dim]Output file:[/] {output_path}",
            title="Export Complete",
            border_style="green",
        )
    )

    # Per-section breakdown table
    console.print()
    table = Table(title="Per-Section Breakdown", show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Section", style="white")
    table.add_column("Basic", justify="right", style="green")
    table.add_column("Cloze", justify="right", style="blue")
    table.add_column("Total", justify="right", style="yellow")

    for num, title, basic, cloze in stats.chapters:
        # Truncate long titles
        display_title = title[:40] + "..." if len(title) > 40 else title
        table.add_row(
            str(num),
            display_title,
            str(basic),
            str(cloze),
            str(basic + cloze),
        )

    # Add totals row
    table.add_section()
    table.add_row(
        "",
        "[bold]Total[/]",
        f"[bold]{stats.total_basic}[/]",
        f"[bold]{stats.total_cloze}[/]",
        f"[bold]{stats.total_cards}[/]",
    )

    console.print(table)
    console.print()


def execute_export(
    chapters_dir: Path,
    output_file: Path | None,
    console: Console,
    quiet: bool = False,
) -> None:
    """Execute the export command."""
    # Find all card files
    card_files = find_card_files(chapters_dir)

    if not card_files:
        console.print(f"[red]No card files found in {chapters_dir}[/]")
        console.print("[dim]Make sure you've run 'anki-gen generate' first.[/]")
        return

    # Load manifest for book metadata
    manifest = load_manifest(chapters_dir)
    if not manifest:
        console.print(f"[red]manifest.json not found in {chapters_dir}[/]")
        console.print("[dim]Make sure you've run 'anki-gen parse' first.[/]")
        return

    # Parse all card files
    chapters: list[ChapterCards] = []
    for path in card_files:
        parsed = parse_card_file(path)
        if parsed:
            chapters.append(parsed)

    if not chapters:
        console.print("[red]No valid card files found[/]")
        return

    # Sort by chapter number
    chapters.sort(key=lambda c: c.chapter_num)

    if not quiet:
        console.print(f"[dim]Book:[/] {manifest.book_title}")
        console.print(f"[dim]Found {len(chapters)} section(s) with cards[/]")

    # Build book slug for tags
    book_slug = re.sub(r"[^a-z0-9-]", "", manifest.book_title.lower().replace(" ", "-"))
    book_slug = re.sub(r"-+", "-", book_slug).strip("-")

    # Build combined export
    combined = build_combined_export(chapters, book_slug)

    # Determine output path
    if output_file is None:
        output_file = chapters_dir / "all_cards.txt"

    # Write output
    output_file.write_text(combined)

    # Display stats
    if not quiet:
        stats = calculate_stats(chapters)
        display_stats(stats, output_file, console)
    else:
        console.print(f"[green]Exported to {output_file}[/]")
