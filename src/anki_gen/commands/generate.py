"""Generate command implementation."""

import json
import re
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from anki_gen.core.flashcard_generator import FlashcardGenerator, GeminiError
from anki_gen.models.flashcard import AnkiExportConfig, GenerationResult
from anki_gen.models.output import BookOutput, ChapterOutput


def find_chapter_files(chapters_dir: Path) -> list[Path]:
    """Find all chapter JSON files in directory.

    Excludes metadata files (*_meta.json) and card files (*_cards.txt).
    """
    all_files = chapters_dir.glob("chapter_*.json")
    # Filter out meta files (e.g., chapter_001_meta.json)
    chapter_files = [f for f in all_files if not f.stem.endswith("_meta")]
    return sorted(chapter_files)


def is_chapter_generated(chapter_path: Path) -> bool:
    """Check if a chapter has already been generated (has _cards.txt file)."""
    cards_path = chapter_path.parent / f"{chapter_path.stem}_cards.txt"
    return cards_path.exists()


def parse_chapter_selection(selection: str, total_chapters: int) -> set[int]:
    """Parse chapter selection string like '1,3,5-7' into set of indices.

    Returns 1-based chapter numbers.
    """
    if selection.lower() == "all":
        return set(range(1, total_chapters + 1))

    result = set()
    for part in selection.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            start_num = int(start.strip())
            end_num = int(end.strip())
            result.update(range(start_num, end_num + 1))
        else:
            result.add(int(part))

    return result


def filter_chapter_files(chapter_files: list[Path], selection: str | None) -> list[Path]:
    """Filter chapter files based on selection string.

    If selection is None, returns all files.
    """
    if selection is None:
        return chapter_files

    selected_nums = parse_chapter_selection(selection, len(chapter_files))

    filtered = []
    for path in chapter_files:
        # Extract chapter number from filename (chapter_001.json -> 1)
        try:
            num_str = path.stem.replace("chapter_", "")
            chapter_num = int(num_str)
            if chapter_num in selected_nums:
                filtered.append(path)
        except ValueError:
            continue

    return filtered


def load_chapter(path: Path) -> ChapterOutput:
    """Load a chapter JSON file."""
    return ChapterOutput.model_validate_json(path.read_text())


def load_manifest(chapters_dir: Path) -> BookOutput:
    """Load the manifest.json file from chapters directory."""
    manifest_path = chapters_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"manifest.json not found in {chapters_dir}. "
            "Make sure you've run 'anki-gen parse' first."
        )
    return BookOutput.model_validate_json(manifest_path.read_text())


def extract_chapter_number(chapter_path: Path) -> int:
    """Extract chapter number from filename (chapter_011.json -> 11)."""
    match = re.search(r"chapter_(\d+)", chapter_path.stem)
    if match:
        return int(match.group(1))
    return 0


def build_deck_name(
    book_title: str,
    chapter_title: str,
    deck_override: str | None = None,
) -> str:
    """Build hierarchical deck name for Anki.

    Format: {Book Title}::{Chapter Title}
    Uses the actual TOC title without confusing index numbers.
    """
    if deck_override:
        return deck_override

    # Sanitize book title (remove :: to avoid hierarchy conflicts)
    safe_book = AnkiExportConfig.sanitize_deck_name(book_title)
    # Truncate if too long
    if len(safe_book) > 50:
        safe_book = safe_book[:47] + "..."

    # Sanitize chapter title
    safe_chapter = AnkiExportConfig.sanitize_deck_name(chapter_title)
    if len(safe_chapter) > 50:
        safe_chapter = safe_chapter[:47] + "..."

    return f"{safe_book}::{safe_chapter}"


def build_export_config(
    manifest: BookOutput,
    chapter_path: Path,
    chapter: ChapterOutput,
    deck_override: str | None = None,
    extra_tags: list[str] | None = None,
) -> AnkiExportConfig:
    """Build export configuration for a chapter."""
    chapter_num = extract_chapter_number(chapter_path)
    chapter_id = f"ch{chapter_num:03d}"

    deck_name = build_deck_name(
        book_title=manifest.book_title,
        chapter_title=chapter.metadata.title,
        deck_override=deck_override,
    )

    book_slug = AnkiExportConfig.slugify(manifest.book_title)

    return AnkiExportConfig(
        deck_name=deck_name,
        global_tags=extra_tags or [],
        book_slug=book_slug,
        chapter_id=chapter_id,
    )


def save_generation_result(
    result: GenerationResult,
    chapter_path: Path,
    config: AnkiExportConfig,
) -> tuple[Path, Path]:
    """Save generation results to files.

    Returns paths to: (cards_txt, metadata_json)
    """
    chapter_dir = chapter_path.parent
    base_name = chapter_path.stem

    # Save combined cards file
    cards_path = chapter_dir / f"{base_name}_cards.txt"
    cards_content = result.to_combined_txt(config)
    cards_path.write_text(cards_content)

    # Save metadata
    meta_path = chapter_dir / f"{base_name}_meta.json"
    meta_path.write_text(result.metadata.model_dump_json(indent=2))

    return cards_path, meta_path


def execute_generate(
    chapters_dir: Path,
    max_cards: int | None,
    model: str,
    dry_run: bool,
    quiet: bool,
    console: Console,
    chapters: str | None = None,
    deck: str | None = None,
    tags: list[str] | None = None,
    force: bool = False,
) -> None:
    """Execute the generate command."""
    # Load manifest (required for book metadata)
    try:
        manifest = load_manifest(chapters_dir)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/] {e}")
        return

    all_chapter_files = find_chapter_files(chapters_dir)
    selected_files = filter_chapter_files(all_chapter_files, chapters)

    if not selected_files:
        console.print(f"[red]No section files found in {chapters_dir}[/]")
        console.print("[dim]Make sure you've run 'anki-gen parse' first.[/]")
        return

    # Split into already-generated and pending
    already_generated = [f for f in selected_files if is_chapter_generated(f)]
    pending_files = [f for f in selected_files if not is_chapter_generated(f)]

    # Determine which files to process
    if force:
        chapter_files = selected_files
        skipped_files: list[Path] = []
    else:
        chapter_files = pending_files
        skipped_files = already_generated

    if not quiet:
        book_title_display = manifest.book_title[:60]
        if len(manifest.book_title) > 60:
            book_title_display += "..."
        console.print(f"[dim]Book:[/] {book_title_display}")
        console.print(f"[dim]Model: {model}[/]")
        if deck:
            console.print(f"[dim]Deck override: {deck}[/]")
        if tags:
            console.print(f"[dim]Extra tags: {', '.join(tags)}[/]")

        # Show generation status
        if force:
            console.print(f"[dim]Sections to process:[/] {len(chapter_files)} (force mode)")
        else:
            console.print(
                f"[dim]Sections:[/] {len(pending_files)} pending, "
                f"{len(already_generated)} already generated"
            )
        console.print()

    # Handle case where all chapters are already generated
    if not chapter_files and not dry_run:
        console.print("[green]All sections already generated![/]")
        console.print("[dim]Use --force to regenerate.[/]")
        return

    if dry_run:
        console.print("[yellow]Dry run mode - no API calls will be made[/]")
        console.print()

        if skipped_files:
            table = Table(title=f"Already Generated ({len(skipped_files)})", title_style="dim")
            table.add_column("#", style="dim", width=4)
            table.add_column("Section", style="dim")
            table.add_column("Words", justify="right", style="dim")

            for path in skipped_files:
                chapter = load_chapter(path)
                section_num = extract_chapter_number(path)
                short_title = chapter.metadata.title[:45]
                if len(chapter.metadata.title) > 45:
                    short_title += "..."
                table.add_row(
                    str(section_num),
                    f"✓ {short_title}",
                    f"{chapter.metadata.word_count:,}",
                )

            console.print(table)
            console.print()

        if chapter_files:
            table = Table(title=f"To Generate ({len(chapter_files)})", title_style="cyan bold")
            table.add_column("#", style="cyan", width=4)
            table.add_column("Section", style="cyan")
            table.add_column("Words", justify="right", style="white")
            table.add_column("Deck", style="dim")

            for path in chapter_files:
                chapter = load_chapter(path)
                config = build_export_config(manifest, path, chapter, deck, tags)
                section_num = extract_chapter_number(path)
                short_title = chapter.metadata.title[:40]
                if len(chapter.metadata.title) > 40:
                    short_title += "..."
                # Shorten deck name for display
                deck_display = config.deck_name
                if len(deck_display) > 35:
                    deck_display = "..." + deck_display[-32:]
                table.add_row(
                    str(section_num),
                    short_title,
                    f"{chapter.metadata.word_count:,}",
                    deck_display,
                )

            console.print(table)
        else:
            console.print("[green]Nothing to generate - all sections complete![/]")
            console.print("[dim]Use --force to regenerate.[/]")

        return

    # Create book slug for unique GUIDs across books
    book_slug = AnkiExportConfig.slugify(manifest.book_title)

    generator = FlashcardGenerator(
        model=model,
        max_cards=max_cards,
        console=console,
        stream=not quiet,
        book_slug=book_slug,
    )

    results: list[tuple[str, int, int]] = []  # (title, basic_count, cloze_count)
    errors: list[tuple[str, str]] = []  # (title, error_message)

    for i, chapter_path in enumerate(chapter_files):
        chapter = load_chapter(chapter_path)
        title = chapter.metadata.title
        short_title = title[:50] + "..." if len(title) > 50 else title
        section_index = extract_chapter_number(chapter_path)

        if not quiet:
            console.print(f"\n[bold cyan][{section_index}/{len(all_chapter_files)}][/] {short_title}")

        try:
            # Generate cards
            result = generator.generate(chapter, chapter_path.name)

            # Build export config
            config = build_export_config(manifest, chapter_path, chapter, deck, tags)

            # Save combined file
            save_generation_result(result, chapter_path, config)
            results.append((title, result.metadata.basic_count, result.metadata.cloze_count))

            if not quiet:
                console.print(
                    f"  [green]✓[/] Generated [green]{result.metadata.basic_count}[/] basic, "
                    f"[blue]{result.metadata.cloze_count}[/] cloze cards"
                )

        except GeminiError as e:
            errors.append((title, str(e)))
            if not quiet:
                console.print(f"  [red]✗[/] Error: {e}")

        except Exception as e:
            errors.append((title, f"Unexpected error: {e}"))
            if not quiet:
                console.print(f"  [red]✗[/] Unexpected error: {e}")

    # Summary
    if not quiet:
        console.print()

        if results:
            total_basic = sum(r[1] for r in results)
            total_cloze = sum(r[2] for r in results)

            console.print(
                Panel(
                    f"[green]Generated flashcards for {len(results)} section(s)[/]\n\n"
                    f"[dim]Total basic cards:[/] {total_basic}\n"
                    f"[dim]Total cloze cards:[/] {total_cloze}\n"
                    f"[dim]Total cards:[/] {total_basic + total_cloze}\n"
                    f"[dim]Output directory:[/] {chapters_dir}",
                    title="Complete",
                    border_style="green",
                )
            )

            console.print()
            console.print("[dim]Per-section breakdown:[/]")
            for title, basic_count, cloze_count in results:
                short_title = title[:50] + "..." if len(title) > 50 else title
                console.print(f"  {short_title}")
                console.print(f"    [green]{basic_count}[/] basic, [blue]{cloze_count}[/] cloze = {basic_count + cloze_count} total")

        if errors:
            console.print()
            console.print(f"[red]Failed to process {len(errors)} section(s):[/]")
            for title, error in errors:
                short_title = title[:50] + "..." if len(title) > 50 else title
                console.print(f"  [red]{short_title}[/]")
                console.print(f"    {error}")
