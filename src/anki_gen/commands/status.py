"""Status command implementation."""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from anki_gen.models.output import BookOutput, ChapterOutput


@dataclass
class SectionStatus:
    """Status of a single section."""

    section_num: int
    title: str
    word_count: int
    is_parsed: bool
    is_generated: bool
    basic_count: int
    cloze_count: int


@dataclass
class DirectoryStatus:
    """Overall status of a chapters directory."""

    book_title: str
    authors: list[str]
    total_epub_sections: int
    output_directory: Path
    created_at: datetime | None
    sections: list[SectionStatus]
    export_exists: bool
    export_card_count: int


def find_parsed_sections(chapters_dir: Path) -> dict[int, Path]:
    """Find all parsed section JSON files.

    Returns: dict mapping section number to file path
    """
    result = {}
    for path in chapters_dir.glob("chapter_*.json"):
        if path.name == "manifest.json":
            continue
        match = re.search(r"chapter_(\d+)\.json$", path.name)
        if match:
            result[int(match.group(1))] = path
    return result


def find_generated_sections(chapters_dir: Path) -> dict[int, Path]:
    """Find all generated card files.

    Returns: dict mapping section number to file path
    """
    result = {}
    for path in chapters_dir.glob("chapter_*_cards.txt"):
        match = re.search(r"chapter_(\d+)_cards\.txt$", path.name)
        if match:
            result[int(match.group(1))] = path
    return result


def count_cards_in_file(path: Path) -> tuple[int, int]:
    """Count basic and cloze cards in a card file.

    Returns: (basic_count, cloze_count)
    """
    content = path.read_text()
    basic_count = 0
    cloze_count = 0

    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("Basic|"):
            basic_count += 1
        elif line.startswith("Cloze|"):
            cloze_count += 1

    return basic_count, cloze_count


def count_export_cards(export_path: Path) -> int:
    """Count total cards in export file."""
    if not export_path.exists():
        return 0

    content = export_path.read_text()
    count = 0
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("Basic|") or line.startswith("Cloze|"):
            count += 1
    return count


def load_manifest(chapters_dir: Path) -> BookOutput | None:
    """Load the manifest.json file from chapters directory."""
    manifest_path = chapters_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    return BookOutput.model_validate_json(manifest_path.read_text())


def load_chapter(path: Path) -> ChapterOutput:
    """Load a chapter JSON file."""
    return ChapterOutput.model_validate_json(path.read_text())


def get_directory_status(chapters_dir: Path) -> DirectoryStatus | None:
    """Get comprehensive status of a chapters directory."""
    manifest = load_manifest(chapters_dir)
    if not manifest:
        return None

    parsed_sections = find_parsed_sections(chapters_dir)
    generated_sections = find_generated_sections(chapters_dir)

    # Build section status list
    sections: list[SectionStatus] = []

    # Get all section numbers (parsed or generated)
    all_section_nums = sorted(set(parsed_sections.keys()) | set(generated_sections.keys()))

    for section_num in all_section_nums:
        is_parsed = section_num in parsed_sections
        is_generated = section_num in generated_sections

        # Get title and word count from parsed file
        title = f"Section {section_num}"
        word_count = 0
        if is_parsed:
            try:
                chapter = load_chapter(parsed_sections[section_num])
                title = chapter.metadata.title
                word_count = chapter.metadata.word_count
            except Exception:
                pass

        # Get card counts from generated file
        basic_count = 0
        cloze_count = 0
        if is_generated:
            try:
                basic_count, cloze_count = count_cards_in_file(
                    generated_sections[section_num]
                )
            except Exception:
                pass

        sections.append(
            SectionStatus(
                section_num=section_num,
                title=title,
                word_count=word_count,
                is_parsed=is_parsed,
                is_generated=is_generated,
                basic_count=basic_count,
                cloze_count=cloze_count,
            )
        )

    # Check export status
    export_path = chapters_dir / "all_cards.txt"
    export_exists = export_path.exists()
    export_card_count = count_export_cards(export_path) if export_exists else 0

    return DirectoryStatus(
        book_title=manifest.book_title,
        authors=manifest.authors,
        total_epub_sections=manifest.total_chapters,
        output_directory=chapters_dir,
        created_at=manifest.created_at,
        sections=sections,
        export_exists=export_exists,
        export_card_count=export_card_count,
    )


def display_status(status: DirectoryStatus, console: Console) -> None:
    """Display status in a formatted way."""
    # Book info panel
    console.print()

    authors_str = ", ".join(status.authors) if status.authors else "Unknown"
    created_str = (
        status.created_at.strftime("%Y-%m-%d %H:%M")
        if status.created_at
        else "Unknown"
    )

    parsed_count = sum(1 for s in status.sections if s.is_parsed)
    generated_count = sum(1 for s in status.sections if s.is_generated)
    total_basic = sum(s.basic_count for s in status.sections)
    total_cloze = sum(s.cloze_count for s in status.sections)
    total_cards = total_basic + total_cloze

    # Determine overall status
    if generated_count == 0 and parsed_count == 0:
        overall_status = "[dim]Not started[/]"
    elif generated_count == 0:
        overall_status = "[yellow]Parsed only[/]"
    elif status.export_exists:
        overall_status = "[green]Exported[/]"
    else:
        overall_status = "[blue]Generated[/]"

    console.print(
        Panel(
            f"[bold]{status.book_title}[/]\n\n"
            f"[dim]Author(s):[/] {authors_str}\n"
            f"[dim]Output directory:[/] {status.output_directory}\n"
            f"[dim]Created:[/] {created_str}\n\n"
            f"[dim]EPUB total sections:[/] {status.total_epub_sections}\n"
            f"[dim]Status:[/] {overall_status}",
            title="Book Information",
            border_style="green",
        )
    )

    # Progress summary
    console.print()
    console.print(
        Panel(
            f"[dim]Sections parsed:[/] {parsed_count} of {status.total_epub_sections}\n"
            f"[dim]Sections generated:[/] {generated_count} of {parsed_count}\n"
            f"[dim]Total cards:[/] {total_cards} ([green]{total_basic}[/] basic, [blue]{total_cloze}[/] cloze)\n"
            f"[dim]Exported:[/] {'[green]Yes[/] (' + str(status.export_card_count) + ' cards)' if status.export_exists else '[dim]No[/]'}",
            title="Progress Summary",
            border_style="cyan",
        )
    )

    # Section details table
    if status.sections:
        console.print()
        table = Table(
            title="Section Details",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("#", style="dim", width=4)
        table.add_column("Title", style="white", max_width=40)
        table.add_column("Words", justify="right", style="dim")
        table.add_column("Parsed", justify="center", width=6)
        table.add_column("Generated", justify="center", width=9)
        table.add_column("Basic", justify="right", style="green", width=6)
        table.add_column("Cloze", justify="right", style="blue", width=6)
        table.add_column("Total", justify="right", style="yellow", width=6)

        for section in status.sections:
            # Truncate long titles
            display_title = (
                section.title[:37] + "..." if len(section.title) > 40 else section.title
            )
            parsed_mark = "[green]✓[/]" if section.is_parsed else "[dim]—[/]"
            generated_mark = "[green]✓[/]" if section.is_generated else "[dim]—[/]"

            total = section.basic_count + section.cloze_count

            table.add_row(
                str(section.section_num),
                display_title,
                f"{section.word_count:,}" if section.word_count else "—",
                parsed_mark,
                generated_mark,
                str(section.basic_count) if section.is_generated else "—",
                str(section.cloze_count) if section.is_generated else "—",
                str(total) if section.is_generated else "—",
            )

        # Add totals row
        table.add_section()
        table.add_row(
            "",
            "[bold]Total[/]",
            "",
            f"[bold]{parsed_count}[/]",
            f"[bold]{generated_count}[/]",
            f"[bold]{total_basic}[/]",
            f"[bold]{total_cloze}[/]",
            f"[bold]{total_cards}[/]",
        )

        console.print(table)

    # Next steps hint
    console.print()
    if parsed_count == 0:
        console.print(
            "[dim]Next step:[/] Run [cyan]anki-gen parse <epub>[/] to extract sections"
        )
    elif generated_count < parsed_count:
        ungened = parsed_count - generated_count
        console.print(
            f"[dim]Next step:[/] Run [cyan]anki-gen generate {status.output_directory}[/] "
            f"to generate cards for {ungened} remaining section(s)"
        )
    elif not status.export_exists:
        console.print(
            f"[dim]Next step:[/] Run [cyan]anki-gen export {status.output_directory}[/] "
            "to create combined import file"
        )
    else:
        console.print(
            f"[green]Complete![/] Import [cyan]{status.output_directory / 'all_cards.txt'}[/] into Anki"
        )
    console.print()


def execute_status(
    chapters_dir: Path,
    console: Console,
) -> None:
    """Execute the status command."""
    status = get_directory_status(chapters_dir)

    if not status:
        console.print(f"[red]manifest.json not found in {chapters_dir}[/]")
        console.print("[dim]Make sure you've run 'anki-gen parse' first.[/]")
        return

    display_status(status, console)
