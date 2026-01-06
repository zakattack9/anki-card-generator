"""Generate command implementation."""

from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from anki_gen.core.flashcard_generator import FlashcardGenerator, GeminiError
from anki_gen.models.flashcard import GenerationResult
from anki_gen.models.output import ChapterOutput


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


def save_generation_result(result: GenerationResult, chapter_path: Path) -> tuple[Path, Path, Path]:
    """Save generation results to files.

    Returns paths to: (basic_txt, cloze_txt, metadata_json)
    """
    chapter_dir = chapter_path.parent
    # Use chapter filename as base (e.g., chapter_001 -> chapter_001_basic.txt)
    base_name = chapter_path.stem

    # Save basic cards
    basic_path = chapter_dir / f"{base_name}_basic.txt"
    basic_content = result.to_basic_txt()
    if basic_content:
        basic_path.write_text(basic_content)
    else:
        basic_path = None

    # Save cloze cards
    cloze_path = chapter_dir / f"{base_name}_cloze.txt"
    cloze_content = result.to_cloze_txt()
    if cloze_content:
        cloze_path.write_text(cloze_content)
    else:
        cloze_path = None

    # Save metadata
    meta_path = chapter_dir / f"{base_name}_meta.json"
    meta_path.write_text(result.metadata.model_dump_json(indent=2))

    return basic_path, cloze_path, meta_path


def execute_generate(
    chapters_dir: Path,
    max_cards: int | None,
    model: str,
    dry_run: bool,
    quiet: bool,
    console: Console,
    chapters: str | None = None,
) -> None:
    """Execute the generate command."""
    all_chapter_files = find_chapter_files(chapters_dir)
    chapter_files = filter_chapter_files(all_chapter_files, chapters)

    if not chapter_files:
        console.print(f"[red]No chapter files found in {chapters_dir}[/]")
        console.print("[dim]Make sure you've run 'anki-gen parse' first.[/]")
        return

    if not quiet:
        console.print(f"[dim]Found {len(chapter_files)} chapter(s) to process[/]")
        console.print(f"[dim]Model: {model}[/]")
        console.print()

    if dry_run:
        console.print("[yellow]Dry run mode - no API calls will be made[/]")
        console.print()
        for path in chapter_files:
            chapter = load_chapter(path)
            console.print(f"  Would process: [cyan]{chapter.metadata.title}[/]")
            console.print(f"    Words: {chapter.metadata.word_count:,}")
        return

    generator = FlashcardGenerator(
        model=model,
        max_cards=max_cards,
        console=console,
        stream=not quiet,
    )

    results: list[tuple[str, int, int]] = []  # (title, basic_count, cloze_count)
    errors: list[tuple[str, str]] = []  # (title, error_message)

    # When streaming, we show a Live panel per generation, so don't use Progress spinner
    # Progress spinner is only used in quiet mode (no streaming display)
    for i, chapter_path in enumerate(chapter_files):
        chapter = load_chapter(chapter_path)
        title = chapter.metadata.title
        short_title = title[:50] + "..." if len(title) > 50 else title

        if not quiet:
            console.print(f"\n[bold cyan]Chapter {i + 1}/{len(chapter_files)}:[/] {short_title}")

        try:
            result = generator.generate(chapter, chapter_path.name)
            save_generation_result(result, chapter_path)
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
                console.print(f"    [green]{basic_count}[/] basic, [blue]{cloze_count}[/] cloze")

        if errors:
            console.print()
            console.print(f"[red]Failed to process {len(errors)} chapter(s):[/]")
            for title, error in errors:
                short_title = title[:50] + "..." if len(title) > 50 else title
                console.print(f"  [red]{short_title}[/]")
                console.print(f"    {error}")
