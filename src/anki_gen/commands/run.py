"""Interactive run command wizard for the complete flashcard generation workflow.

This module provides both an interactive Textual TUI and a non-interactive mode
for the complete flashcard generation workflow (parse → generate → export).
"""

from __future__ import annotations

import re
import signal
from collections import defaultdict
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn


def execute_run(
    book_path: Path | None,
    non_interactive: bool,
    force: bool,
    console: Console,
) -> None:
    """Execute the run command.

    Args:
        book_path: Path to book file (PDF/EPUB). If None, shows file picker.
        non_interactive: If True, skip TUI and use defaults.
        force: If True, force regenerate all sections.
        console: Rich console for output.
    """
    if non_interactive:
        # Non-interactive mode requires book path
        if book_path is None:
            console.print("[red]Error: --yes requires a book path argument[/]")
            console.print("[dim]Usage: anki-gen run book.pdf --yes[/]")
            raise SystemExit(1)

        _run_non_interactive(book_path, force, console)
    else:
        # Launch Textual TUI
        from anki_gen.tui import RunWizardApp

        app = RunWizardApp(book_path=book_path, force=force)
        app.run()


def _run_non_interactive(
    book_path: Path,
    force: bool,
    console: Console,
) -> None:
    """Run the pipeline in non-interactive mode with defaults.

    Non-interactive mode defaults:
    - Selects ALL sections at maximum depth level
    - Deck hierarchy: Maximum depth (most granular deck names)
    - Output directory: current directory (./)
    - Model: gemini-3-pro-preview
    - Deck name: Auto-generated
    - Max cards: Unlimited
    - Tags: None
    - Skip already-generated sections (unless --force specified)
    - Export format: anki-txt (fixed)
    """
    from anki_gen.cache.manager import CacheManager
    from anki_gen.commands.export import (
        build_combined_export,
        calculate_stats,
        find_card_files,
        parse_card_file,
    )
    from anki_gen.commands.generate import (
        execute_generate,
        extract_chapter_number,
        find_chapter_files,
        is_chapter_generated,
    )
    from anki_gen.core.output_writer import OutputWriter
    from anki_gen.core.parser_factory import ParserFactory

    # Validate book path
    if not book_path.exists():
        console.print(f"[red]Error: File not found: {book_path}[/]")
        raise SystemExit(1)

    if not ParserFactory.is_supported(book_path):
        console.print(f"[red]Error: Unsupported file format: {book_path.suffix}[/]")
        console.print("[dim]Supported formats: .pdf, .epub[/]")
        raise SystemExit(1)

    # Parse the book
    console.print(f"[bold]Processing:[/] {book_path.name}")
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Parsing book...", total=None)

        cache_manager = CacheManager(book_path.parent)
        cached = cache_manager.get_cached_structure(book_path)

        parser = ParserFactory.create(book_path)
        parsed = parser.parse()

        if not cached:
            cache_manager.save_structure(book_path, parsed)

    # Get chapters directory
    stem = book_path.stem
    clean_stem = re.sub(r"[^\w\s-]", "", stem).strip()
    clean_stem = re.sub(r"[-\s]+", "_", clean_stem)
    chapters_dir = book_path.parent / f"{clean_stem}_chapters"

    # Select all sections at max depth
    all_indices = list(range(len(parsed.chapters)))

    # Calculate max depth
    max_depth = 1
    for chapter in parsed.chapters:
        max_depth = max(max_depth, chapter.level + 1)

    console.print(f"[bold cyan][1/3][/] Parsing...")

    # Step 1: Parse - extract chapters if needed
    if not chapters_dir.exists():
        writer = OutputWriter(chapters_dir, book_path)
        chapter_metadata = []

        for idx in all_indices:
            chapter = parsed.chapters[idx]
            _, metadata = writer.write_chapter(chapter, "markdown")
            chapter_metadata.append(metadata)

        writer.write_manifest(parsed, all_indices, chapter_metadata)
        console.print(f"  [green]\u2713[/] Extracted {len(all_indices)} sections to {chapters_dir}/")
    else:
        # Check for new sections
        existing_files = set(f.stem for f in find_chapter_files(chapters_dir))
        new_indices = []
        for idx in all_indices:
            chapter_stem = f"chapter_{idx + 1:03d}"
            if chapter_stem not in existing_files:
                new_indices.append(idx)

        if new_indices:
            writer = OutputWriter(chapters_dir, book_path)
            for idx in new_indices:
                chapter = parsed.chapters[idx]
                writer.write_chapter(chapter, "markdown")
            console.print(f"  [green]\u2713[/] Extracted {len(new_indices)} new sections")
        else:
            console.print(f"  [green]\u2713[/] Using existing sections in {chapters_dir}/")

    console.print()

    # Step 2: Generate
    console.print("[bold cyan][2/3][/] Generating flashcards...")

    # Get generation status
    gen_status = {}
    chapter_files = find_chapter_files(chapters_dir)
    for f in chapter_files:
        match = re.search(r"chapter_(\d+)", f.stem)
        if match:
            idx = int(match.group(1)) - 1
            gen_status[idx] = is_chapter_generated(f)

    to_generate = [
        idx for idx in all_indices if force or not gen_status.get(idx, False)
    ]

    if not to_generate:
        console.print("  [green]\u2713[/] All sections already generated")
    else:
        # Build section tree for deck names
        from anki_gen.tui.state import (
            SectionNode,
            calculate_deck_name_for_chapter,
            get_ancestors_to_depth,
        )

        # Build simple tree for depth-based deck names
        nodes: list[SectionNode] = []
        root_nodes: list[SectionNode] = []
        node_stack: list[SectionNode] = []

        for chapter in parsed.chapters:
            node = SectionNode(
                index=chapter.index,
                title=chapter.title,
                word_count=chapter.word_count,
                level=chapter.level,
                status="pending",
            )
            nodes.append(node)

            while node_stack and node_stack[-1].level >= node.level:
                node_stack.pop()

            if node_stack:
                parent = node_stack[-1]
                node.parent = parent
                parent.children.append(node)
            else:
                root_nodes.append(node)

            node_stack.append(node)

        # Group chapters by deck name at max depth
        deck_groups: dict[str, list[int]] = defaultdict(list)
        for idx in to_generate:
            deck_name = calculate_deck_name_for_chapter(
                idx, root_nodes, max_depth, parsed.metadata.title
            )
            deck_groups[deck_name].append(idx)

        # Generate for each deck group
        quiet_console = Console(quiet=True)
        for deck_name, chapter_indices in deck_groups.items():
            execute_generate(
                chapters_dir=chapters_dir,
                max_cards=None,
                model="gemini-3-pro-preview",
                dry_run=False,
                quiet=True,
                console=quiet_console,
                chapters=",".join(str(idx + 1) for idx in chapter_indices),
                deck=deck_name,
                tags=None,
                force=force,
            )

        console.print(f"  [green]\u2713[/] Generated cards for {len(to_generate)} sections")

    console.print()

    # Step 3: Export
    console.print("[bold cyan][3/3][/] Exporting...")

    output_file = Path(".") / "all_cards.txt"

    card_files = find_card_files(chapters_dir)
    selected_card_files = []
    for path in card_files:
        chapter_num = extract_chapter_number(path)
        if chapter_num is not None and (chapter_num - 1) in set(all_indices):
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
        console.print(f"  [green]\u2713[/] Exported {stats.total_cards} cards to {output_file}")
    else:
        console.print("  [yellow]No cards to export[/]")

    console.print()

    # Final summary
    if chapters_data:
        summary_lines = [
            f"  Total cards: {stats.total_cards} ({stats.basic_count} basic, {stats.cloze_count} cloze)",
            "",
            f"  Import file: {output_file}",
            "",
            "  [dim]Next: Import into Anki via File \u2192 Import[/]",
        ]

        console.print(Panel(
            "\n".join(summary_lines),
            title="Complete",
            border_style="green",
        ))
