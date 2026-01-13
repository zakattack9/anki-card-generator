"""Pipeline logic for the run wizard - parse, generate, export."""

from __future__ import annotations

import hashlib
import re
import signal
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anki_gen.models.book import ParsedBook
    from anki_gen.tui.state import RunConfig, SectionNode

# Large book threshold for warning
LARGE_BOOK_THRESHOLD = 100

# Deck hierarchy level names for preview
DECK_LEVEL_NAMES = ["Book", "Part", "Chapter", "Section", "Subsection"]


class InterruptedError(Exception):
    """Raised when execution is interrupted by user."""

    pass


def scan_for_books(directory: Path) -> list[Path]:
    """Find all .pdf and .epub files in directory."""
    books = []
    for ext in ["*.pdf", "*.epub"]:
        books.extend(directory.glob(ext))
    return sorted(books, key=lambda p: p.name.lower())


def get_deck_hierarchy_preview(depth_level: int) -> str:
    """Get deck hierarchy preview string based on depth level."""
    levels = DECK_LEVEL_NAMES[: depth_level + 1]
    return "::".join(levels)


def calculate_file_hash(file_path: Path) -> str:
    """Calculate MD5 hash of a file."""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def validate_output_dir(path: Path) -> tuple[Path, str | None]:
    """Validate output directory, fall back to current directory if invalid.

    Returns (validated_path, warning_message).
    """
    if path.exists() and path.is_dir():
        return path, None
    elif not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path, None
        except OSError:
            return Path("."), f"Could not create {path}, using current directory"
    else:
        return Path("."), f"{path} is not a directory, using current directory"


def check_book_hash_changed(book_path: Path, chapters_dir: Path) -> tuple[bool, str | None]:
    """Check if book file has changed since last generation."""
    if not chapters_dir.exists():
        return False, None

    manifest_path = chapters_dir / "manifest.json"
    if not manifest_path.exists():
        return False, None

    try:
        import json

        manifest = json.loads(manifest_path.read_text())
        stored_hash = manifest.get("source_hash")

        if stored_hash is None:
            return False, None

        current_hash = calculate_file_hash(book_path)

        if current_hash != stored_hash:
            return True, (
                "Book file has changed since last generation. "
                "Previously generated sections will be regenerated."
            )

        return False, None
    except (json.JSONDecodeError, OSError):
        return False, None


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable form."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def get_default_chapters_dir(book_path: Path) -> Path:
    """Get default chapters directory based on book filename."""
    stem = book_path.stem
    clean_stem = re.sub(r"[^\w\s-]", "", stem).strip()
    clean_stem = re.sub(r"[-\s]+", "_", clean_stem)
    return book_path.parent / f"{clean_stem}_chapters"


def get_generation_status(chapters_dir: Path, chapter_indices: list[int]) -> dict[int, bool]:
    """Check which sections have been generated."""
    from anki_gen.commands.generate import find_chapter_files, is_chapter_generated

    status = {}
    if chapters_dir.exists():
        chapter_files = find_chapter_files(chapters_dir)
        for f in chapter_files:
            match = re.search(r"chapter_(\d+)", f.stem)
            if match:
                idx = int(match.group(1)) - 1
                status[idx] = is_chapter_generated(f)

    for idx in chapter_indices:
        if idx not in status:
            status[idx] = False

    return status


async def run_parse_step(
    book_path: Path,
    parsed: "ParsedBook",
    config: "RunConfig",
    chapters_dir: Path,
    on_progress: callable | None = None,
    check_interrupt: callable | None = None,
) -> int:
    """Run the parse step of the pipeline.

    Returns the number of sections extracted.
    """
    from anki_gen.commands.generate import find_chapter_files
    from anki_gen.core.output_writer import OutputWriter

    if not chapters_dir.exists():
        # Need to parse first
        writer = OutputWriter(chapters_dir, book_path)
        chapter_metadata = []

        for idx in config.selected_indices:
            if check_interrupt and check_interrupt():
                raise InterruptedError()
            chapter = parsed.chapters[idx]
            _, metadata = writer.write_chapter(chapter, "markdown")
            chapter_metadata.append(metadata)

        writer.write_manifest(parsed, config.selected_indices, chapter_metadata)
        return len(config.selected_indices)
    else:
        # Check if we need to extract any new sections
        existing_files = set(f.stem for f in find_chapter_files(chapters_dir))
        new_indices = []
        for idx in config.selected_indices:
            chapter_stem = f"chapter_{idx + 1:03d}"
            if chapter_stem not in existing_files:
                new_indices.append(idx)

        if new_indices:
            writer = OutputWriter(chapters_dir, book_path)

            for idx in new_indices:
                if check_interrupt and check_interrupt():
                    raise InterruptedError()
                chapter = parsed.chapters[idx]
                writer.write_chapter(chapter, "markdown")

            return len(new_indices)
        else:
            return 0


async def run_generate_step(
    parsed: "ParsedBook",
    config: "RunConfig",
    chapters_dir: Path,
    section_tree: "list[SectionNode]",
    on_progress: callable | None = None,
    check_interrupt: callable | None = None,
) -> tuple[int, list[int], list[int]]:
    """Run the generate step of the pipeline.

    Returns (newly_generated_count, to_generate_indices, previously_generated_indices).
    """
    from anki_gen.commands.generate import execute_generate
    from anki_gen.tui.state import calculate_deck_name_for_chapter
    from rich.console import Console

    gen_status = get_generation_status(chapters_dir, config.selected_indices)
    to_generate = [
        idx
        for idx in config.selected_indices
        if config.force_regenerate or not gen_status.get(idx, False)
    ]
    previously_generated = [
        idx
        for idx in config.selected_indices
        if not config.force_regenerate and gen_status.get(idx, False)
    ]

    if not to_generate:
        return 0, to_generate, previously_generated

    # Use a quiet console for the underlying generate command
    quiet_console = Console(quiet=True)

    if config.deck_name is None:
        # Auto mode: use depth-based deck names
        deck_groups: dict[str, list[int]] = defaultdict(list)

        for idx in to_generate:
            deck_name = calculate_deck_name_for_chapter(
                idx, section_tree, config.depth_level, parsed.metadata.title
            )
            deck_groups[deck_name].append(idx)

        total_groups = len(deck_groups)
        for i, (deck_name, chapter_indices) in enumerate(deck_groups.items()):
            if check_interrupt and check_interrupt():
                raise InterruptedError()

            if on_progress:
                on_progress(i, total_groups, deck_name)

            execute_generate(
                chapters_dir=chapters_dir,
                max_cards=config.max_cards,
                model=config.model,
                dry_run=False,
                quiet=True,
                console=quiet_console,
                chapters=",".join(str(idx + 1) for idx in chapter_indices),
                deck=deck_name,
                tags=config.tags or None,
                force=config.force_regenerate,
            )
    else:
        # Custom deck name
        if on_progress:
            on_progress(0, 1, config.deck_name)

        execute_generate(
            chapters_dir=chapters_dir,
            max_cards=config.max_cards,
            model=config.model,
            dry_run=False,
            quiet=True,
            console=quiet_console,
            chapters=",".join(str(idx + 1) for idx in to_generate),
            deck=config.deck_name,
            tags=config.tags or None,
            force=config.force_regenerate,
        )

    return len(to_generate), to_generate, previously_generated


async def run_export_step(
    parsed: "ParsedBook",
    config: "RunConfig",
    chapters_dir: Path,
    output_file: Path,
    on_progress: callable | None = None,
) -> tuple[int, int, int]:
    """Run the export step of the pipeline.

    Returns (total_cards, basic_count, cloze_count).
    """
    from anki_gen.commands.export import (
        build_combined_export,
        calculate_stats,
        find_card_files,
        parse_card_file,
    )
    from anki_gen.commands.generate import extract_chapter_number

    selected_indices_set = set(config.selected_indices)
    card_files = find_card_files(chapters_dir)
    selected_card_files = []

    for path in card_files:
        chapter_num = extract_chapter_number(path)
        if chapter_num is not None and (chapter_num - 1) in selected_indices_set:
            selected_card_files.append(path)

    chapters_data = []
    for path in sorted(selected_card_files, key=lambda p: extract_chapter_number(p) or 0):
        parsed_cards = parse_card_file(path)
        if parsed_cards:
            chapters_data.append(parsed_cards)

    if chapters_data:
        book_slug = re.sub(
            r"[^a-z0-9-]", "", parsed.metadata.title.lower().replace(" ", "-")
        )
        book_slug = re.sub(r"-+", "-", book_slug).strip("-")

        combined = build_combined_export(chapters_data, book_slug)
        output_file.write_text(combined)

        stats = calculate_stats(chapters_data)
        return stats.total_cards, stats.basic_count, stats.cloze_count
    else:
        return 0, 0, 0
