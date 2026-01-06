"""Generate command implementation."""

import json
import re
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from anki_gen.core.flashcard_generator import FlashcardGenerator, GeminiError
from anki_gen.models.flashcard import AnkiExportConfig, GenerationResult
from anki_gen.models.output import BookOutput, ChapterOutput


def find_chapter_files(chapters_dir: Path) -> list[Path]:
    """Find all chapter JSON files in directory."""
    return sorted(chapters_dir.glob("chapter_*.json"))


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
    chapter_num: int,
    deck_override: str | None = None,
) -> str:
    """Build hierarchical deck name for Anki.

    Format: {Book Title}::Chapter {NN} - {Chapter Title}
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
    if len(safe_chapter) > 40:
        safe_chapter = safe_chapter[:37] + "..."

    return f"{safe_book}::Chapter {chapter_num:02d} - {safe_chapter}"


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
        chapter_num=chapter_num,
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
) -> None:
    """Execute the generate command."""
    # Load manifest (required for book metadata)
    try:
        manifest = load_manifest(chapters_dir)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/] {e}")
        return

    all_chapter_files = find_chapter_files(chapters_dir)
    chapter_files = filter_chapter_files(all_chapter_files, chapters)

    if not chapter_files:
        console.print(f"[red]No chapter files found in {chapters_dir}[/]")
        console.print("[dim]Make sure you've run 'anki-gen parse' first.[/]")
        return

    if not quiet:
        console.print(f"[dim]Book:[/] {manifest.book_title[:60]}...")
        console.print(f"[dim]Found {len(chapter_files)} chapter(s) to process[/]")
        console.print(f"[dim]Model: {model}[/]")
        if deck:
            console.print(f"[dim]Deck override: {deck}[/]")
        if tags:
            console.print(f"[dim]Extra tags: {', '.join(tags)}[/]")
        console.print()

    if dry_run:
        console.print("[yellow]Dry run mode - no API calls will be made[/]")
        console.print()
        for path in chapter_files:
            chapter = load_chapter(path)
            chapter_num = extract_chapter_number(path)
            config = build_export_config(manifest, path, chapter, deck, tags)
            console.print(f"  Would process: [cyan]{chapter.metadata.title}[/]")
            console.print(f"    Words: {chapter.metadata.word_count:,}")
            console.print(f"    Deck: {config.deck_name}")
        return

    generator = FlashcardGenerator(
        model=model,
        max_cards=max_cards,
        console=console,
        stream=not quiet,
    )

    results: list[tuple[str, int, int]] = []  # (title, basic_count, cloze_count)
    errors: list[tuple[str, str]] = []  # (title, error_message)

    for i, chapter_path in enumerate(chapter_files):
        chapter = load_chapter(chapter_path)
        title = chapter.metadata.title
        short_title = title[:50] + "..." if len(title) > 50 else title

        if not quiet:
            console.print(f"\n[bold cyan]Chapter {i + 1}/{len(chapter_files)}:[/] {short_title}")

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
                    f"[green]Generated flashcards for {len(results)} chapter(s)[/]\n\n"
                    f"[dim]Total basic cards:[/] {total_basic}\n"
                    f"[dim]Total cloze cards:[/] {total_cloze}\n"
                    f"[dim]Total cards:[/] {total_basic + total_cloze}\n"
                    f"[dim]Output directory:[/] {chapters_dir}",
                    title="Complete",
                    border_style="green",
                )
            )

            console.print()
            console.print("[dim]Per-chapter breakdown:[/]")
            for title, basic_count, cloze_count in results:
                short_title = title[:50] + "..." if len(title) > 50 else title
                console.print(f"  {short_title}")
                console.print(f"    [green]{basic_count}[/] basic, [blue]{cloze_count}[/] cloze = {basic_count + cloze_count} total")

        if errors:
            console.print()
            console.print(f"[red]Failed to process {len(errors)} chapter(s):[/]")
            for title, error in errors:
                short_title = title[:50] + "..." if len(title) > 50 else title
                console.print(f"  [red]{short_title}[/]")
                console.print(f"    {error}")
