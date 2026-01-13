"""Interactive run command wizard for the complete flashcard generation workflow."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

import questionary
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from anki_gen.cache.manager import CacheManager
from anki_gen.commands.generate import (
    build_export_config,
    execute_generate,
    find_chapter_files,
    is_chapter_generated,
    load_chapter,
    load_manifest,
    save_generation_result,
)
from anki_gen.commands.export import execute_export
from anki_gen.core.parser_factory import ParserFactory
from anki_gen.core.output_writer import OutputWriter
from anki_gen.models.book import Chapter, ParsedBook


# Custom questionary style
WIZARD_STYLE = Style([
    ("qmark", "fg:cyan bold"),
    ("question", "bold"),
    ("answer", "fg:cyan bold"),
    ("pointer", "fg:cyan bold"),
    ("highlighted", "fg:cyan bold"),
    ("selected", "fg:green"),
    ("separator", "fg:gray"),
    ("instruction", "fg:gray"),
])


class WizardStep(Enum):
    """Wizard navigation steps."""
    FILE_SELECTION = 1
    SECTION_SELECTION = 2
    CONFIGURATION = 3
    CONFIRMATION = 4
    EXECUTION = 5


class NavigationAction(Enum):
    """User navigation actions."""
    CONTINUE = "continue"
    BACK = "back"
    QUIT = "quit"


@dataclass
class SectionNode:
    """Represents a section in the hierarchical view."""
    index: int
    title: str
    word_count: int
    level: int
    status: Literal["done", "pending", "partial"]
    children: list["SectionNode"] = field(default_factory=list)
    selected: bool = False
    parent: "SectionNode | None" = None


@dataclass
class RunConfig:
    """Configuration for the run command."""
    output_dir: Path = field(default_factory=lambda: Path("."))
    model: str = "gemini-3-pro-preview"
    deck_name: str | None = None  # None = auto
    max_cards: int | None = None  # None = unlimited
    tags: list[str] = field(default_factory=list)
    force_regenerate: bool = False
    selected_indices: list[int] = field(default_factory=list)
    depth_level: int = 1


def scan_for_books(directory: Path) -> list[Path]:
    """Find all .pdf and .epub files in directory."""
    books = []
    for ext in ["*.pdf", "*.epub"]:
        books.extend(directory.glob(ext))
    return sorted(books, key=lambda p: p.name.lower())


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable form."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def get_default_output_dir(book_path: Path) -> Path:
    """Get default output directory based on book filename."""
    stem = book_path.stem
    clean_stem = re.sub(r"[^\w\s-]", "", stem).strip()
    clean_stem = re.sub(r"[-\s]+", "_", clean_stem)
    return book_path.parent / f"{clean_stem}_chapters"


def get_generation_status(chapters_dir: Path, chapter_indices: list[int]) -> dict[int, bool]:
    """Check which sections have been generated."""
    status = {}
    if chapters_dir.exists():
        chapter_files = find_chapter_files(chapters_dir)
        for f in chapter_files:
            # Extract chapter number from filename (chapter_001.md -> 1)
            match = re.search(r"chapter_(\d+)", f.stem)
            if match:
                idx = int(match.group(1)) - 1  # Convert to 0-based index
                status[idx] = is_chapter_generated(f)

    # Fill in missing indices as not generated
    for idx in chapter_indices:
        if idx not in status:
            status[idx] = False

    return status


def build_section_tree(parsed: ParsedBook, chapters_dir: Path | None) -> list[SectionNode]:
    """Build hierarchical section tree with status info."""
    # Get generation status
    chapter_indices = [c.index for c in parsed.chapters]
    gen_status = {}
    if chapters_dir and chapters_dir.exists():
        gen_status = get_generation_status(chapters_dir, chapter_indices)

    # Build flat list first
    nodes: list[SectionNode] = []
    for chapter in parsed.chapters:
        status: Literal["done", "pending", "partial"] = "pending"
        if gen_status.get(chapter.index, False):
            status = "done"

        node = SectionNode(
            index=chapter.index,
            title=chapter.title,
            word_count=chapter.word_count,
            level=chapter.level,
            status=status,
        )
        nodes.append(node)

    # Build hierarchy based on levels
    root_nodes: list[SectionNode] = []
    node_stack: list[SectionNode] = []

    for node in nodes:
        # Pop nodes from stack that are at same or higher level
        while node_stack and node_stack[-1].level >= node.level:
            node_stack.pop()

        if node_stack:
            # This node is a child of the last node in stack
            parent = node_stack[-1]
            node.parent = parent
            parent.children.append(node)
        else:
            # This is a root node
            root_nodes.append(node)

        node_stack.append(node)

    # Update parent statuses based on children
    def update_parent_status(node: SectionNode) -> None:
        if not node.children:
            return

        for child in node.children:
            update_parent_status(child)

        done_count = sum(1 for c in node.children if c.status == "done")
        if done_count == len(node.children):
            node.status = "done"
        elif done_count > 0:
            node.status = "partial"

    for root in root_nodes:
        update_parent_status(root)

    return root_nodes


def get_max_depth(nodes: list[SectionNode]) -> int:
    """Get maximum depth level in the tree."""
    max_level = 0

    def find_max(node: SectionNode) -> None:
        nonlocal max_level
        max_level = max(max_level, node.level)
        for child in node.children:
            find_max(child)

    for node in nodes:
        find_max(node)

    return max_level + 1  # Convert to 1-based


def flatten_to_depth(nodes: list[SectionNode], max_level: int) -> list[SectionNode]:
    """Flatten tree to a specific depth level for display."""
    result: list[SectionNode] = []

    def collect(node: SectionNode, current_level: int) -> None:
        if current_level <= max_level:
            result.append(node)
            if current_level < max_level:
                for child in node.children:
                    collect(child, current_level + 1)

    for node in nodes:
        collect(node, 1)

    return result


def get_all_leaf_indices(nodes: list[SectionNode]) -> list[int]:
    """Get indices of all leaf nodes (lowest level sections)."""
    indices: list[int] = []

    def collect_leaves(node: SectionNode) -> None:
        if not node.children:
            indices.append(node.index)
        else:
            for child in node.children:
                collect_leaves(child)

    for node in nodes:
        collect_leaves(node)

    return indices


def get_selected_leaf_indices(nodes: list[SectionNode]) -> list[int]:
    """Get indices of selected leaf nodes."""
    indices: list[int] = []

    def collect_selected_leaves(node: SectionNode) -> None:
        if not node.children:
            if node.selected:
                indices.append(node.index)
        else:
            for child in node.children:
                collect_selected_leaves(child)

    for node in nodes:
        collect_selected_leaves(node)

    return indices


def calculate_aggregated_word_count(node: SectionNode) -> int:
    """Calculate total word count including all children."""
    if not node.children:
        return node.word_count
    return sum(calculate_aggregated_word_count(child) for child in node.children)


def get_checkbox_state(node: SectionNode) -> str:
    """Get checkbox display state for a node."""
    if not node.children:
        return "[x]" if node.selected else "[ ]"

    # Check children selection state
    selected_count = sum(1 for c in node.children if c.selected or get_partial_selection(c))
    if selected_count == 0:
        return "[ ]"
    elif selected_count == len(node.children) and all(
        get_checkbox_state(c) == "[x]" for c in node.children
    ):
        return "[x]"
    else:
        return "[~]"


def get_partial_selection(node: SectionNode) -> bool:
    """Check if node has partial selection (some but not all children selected)."""
    if not node.children:
        return False

    def count_selected_leaves(n: SectionNode) -> tuple[int, int]:
        if not n.children:
            return (1 if n.selected else 0, 1)
        selected = 0
        total = 0
        for child in n.children:
            s, t = count_selected_leaves(child)
            selected += s
            total += t
        return selected, total

    selected, total = count_selected_leaves(node)
    return 0 < selected < total


def get_status_display(node: SectionNode) -> str:
    """Get status column display for a node."""
    if node.status == "done":
        return "[green]Done[/]"
    elif node.status == "partial":
        # Count done/total children
        done = sum(1 for c in node.children if c.status == "done")
        total = len(node.children)
        return f"[yellow]{done}/{total} done[/]"
    else:
        return "[dim]Pending[/]"


def propagate_selection_down(node: SectionNode, selected: bool) -> None:
    """Propagate selection state to all children."""
    node.selected = selected
    for child in node.children:
        propagate_selection_down(child, selected)


def propagate_selection_up(node: SectionNode) -> None:
    """Update parent selection based on children state."""
    if node.parent:
        # Check if all siblings are in same state
        all_selected = all(c.selected and not get_partial_selection(c) for c in node.parent.children)
        none_selected = all(not c.selected and not get_partial_selection(c) for c in node.parent.children)

        if all_selected:
            node.parent.selected = True
        elif none_selected:
            node.parent.selected = False

        propagate_selection_up(node.parent)


# ============================================================================
# Step 1: File Selection
# ============================================================================

def step_file_selection(
    book_path: Path | None,
    console: Console,
) -> tuple[Path | None, NavigationAction]:
    """Step 1: Select a book file to process."""
    if book_path:
        # Validate provided path
        if not book_path.exists():
            console.print(f"[red]File not found: {book_path}[/]")
            return None, NavigationAction.QUIT

        if not ParserFactory.is_supported(book_path):
            console.print(f"[red]Unsupported file format: {book_path.suffix}[/]")
            console.print("[dim]Supported formats: .pdf, .epub[/]")
            return None, NavigationAction.QUIT

        return book_path, NavigationAction.CONTINUE

    # Scan current directory for books
    books = scan_for_books(Path("."))

    if not books:
        console.print("[red]No PDF or EPUB files found in current directory.[/]")
        console.print("[dim]Supported formats: .pdf, .epub[/]")
        return None, NavigationAction.QUIT

    # Build choices
    choices = []
    for book in books:
        size = format_file_size(book.stat().st_size)
        choices.append(questionary.Choice(
            title=f"{book.name}  ({size})",
            value=book,
        ))
    choices.append(questionary.Choice(title="[Quit]", value=None))

    console.print()
    result = questionary.select(
        "Select a book to process:",
        choices=choices,
        style=WIZARD_STYLE,
        instruction="(Use arrow keys, Enter to select)",
    ).ask()

    if result is None:
        return None, NavigationAction.QUIT

    return result, NavigationAction.CONTINUE


# ============================================================================
# Step 2: Section Selection
# ============================================================================

def step_section_selection(
    parsed: ParsedBook,
    chapters_dir: Path,
    console: Console,
    config: RunConfig,
) -> tuple[list[int], int, NavigationAction]:
    """Step 2: Display book info and select sections."""
    # Build section tree
    section_tree = build_section_tree(parsed, chapters_dir)
    max_depth = get_max_depth(section_tree)

    # If book is flat (all level 0), no depth toggle needed
    has_hierarchy = max_depth > 1
    current_depth = config.depth_level if has_hierarchy else 1

    # Restore previous selections if any
    if config.selected_indices:
        def restore_selection(node: SectionNode) -> None:
            if node.index in config.selected_indices:
                node.selected = True
            for child in node.children:
                restore_selection(child)
        for root in section_tree:
            restore_selection(root)

    while True:
        console.clear()

        # Display book info panel
        info_lines = [
            f"[bold]{parsed.metadata.title}[/]",
            f"[dim]Author(s):[/] {', '.join(parsed.metadata.authors) or 'Unknown'}",
            f"[dim]Format:[/] {parsed.source_format.upper()}",
        ]

        if parsed.source_format == "pdf":
            method_display = parsed.extraction_method.value.replace("_", " ").title()
            info_lines.append(
                f"[dim]Detection:[/] {method_display} "
                f"(confidence: {parsed.extraction_confidence:.0%})"
            )

        info_lines.append(f"[dim]Total Sections:[/] {len(parsed.chapters)}")

        console.print(Panel(
            "\n".join(info_lines),
            title="Book Info",
            border_style="green",
        ))
        console.print()

        # Depth level indicator
        if has_hierarchy:
            console.print(f"[cyan]Section View: Level {current_depth} of {max_depth}[/]  [dim][Press D to change depth][/]")

        # Build section table
        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("", width=4)
        table.add_column("Section", min_width=40)
        table.add_column("Words", justify="right", width=8)
        table.add_column("Status", width=12)

        # Flatten to current depth
        visible_nodes = flatten_to_depth(section_tree, current_depth)

        for node in visible_nodes:
            checkbox = get_checkbox_state(node)

            # Indentation based on level
            indent = "  " * node.level
            if node.children and node.level < current_depth - 1:
                prefix = f"{indent}\u251c\u2500 "  # ├─
            elif node.level > 0:
                prefix = f"{indent}\u2514\u2500 "  # └─
            else:
                prefix = ""

            title_display = f"{prefix}{node.title}"
            if len(title_display) > 45:
                title_display = title_display[:42] + "..."

            word_count = calculate_aggregated_word_count(node)
            status_display = get_status_display(node)

            table.add_row(
                checkbox,
                title_display,
                f"{word_count:,}",
                status_display,
            )

        console.print(table)
        console.print()

        # Instructions
        instructions = "[Space] Toggle  [A] Select All  [N] Select None"
        if has_hierarchy:
            instructions += f"  [D] Depth: {current_depth}\u2192{(current_depth % max_depth) + 1}"
        instructions += "  [Enter] Continue  [B] Back  [Q] Quit"
        console.print(f"[dim]{instructions}[/]")
        console.print()

        # Build selection choices
        choices = []
        for i, node in enumerate(visible_nodes):
            checkbox = get_checkbox_state(node)
            choices.append(questionary.Choice(
                title=f"{checkbox} {node.title}",
                value=("toggle", i),
                checked=node.selected,
            ))

        choices.extend([
            questionary.Choice(title="[A] Select All", value=("all", None)),
            questionary.Choice(title="[N] Select None", value=("none", None)),
        ])
        if has_hierarchy:
            choices.append(questionary.Choice(
                title=f"[D] Change Depth ({current_depth} \u2192 {(current_depth % max_depth) + 1})",
                value=("depth", None)
            ))
        choices.extend([
            questionary.Choice(title="[Enter] Continue", value=("continue", None)),
            questionary.Choice(title="[B] Back", value=("back", None)),
            questionary.Choice(title="[Q] Quit", value=("quit", None)),
        ])

        result = questionary.select(
            "Select sections:",
            choices=choices,
            style=WIZARD_STYLE,
            instruction="",
        ).ask()

        if result is None:
            return [], current_depth, NavigationAction.QUIT

        action, idx = result

        if action == "toggle":
            node = visible_nodes[idx]
            new_state = not node.selected
            propagate_selection_down(node, new_state)
            propagate_selection_up(node)

        elif action == "all":
            for root in section_tree:
                propagate_selection_down(root, True)

        elif action == "none":
            for root in section_tree:
                propagate_selection_down(root, False)

        elif action == "depth":
            current_depth = (current_depth % max_depth) + 1

        elif action == "continue":
            # Get selected leaf indices
            selected = get_selected_leaf_indices(section_tree)
            if not selected:
                console.print("[yellow]Please select at least one section.[/]")
                questionary.press_any_key_to_continue(
                    message="Press any key to continue..."
                ).ask()
                continue
            return selected, current_depth, NavigationAction.CONTINUE

        elif action == "back":
            selected = get_selected_leaf_indices(section_tree)
            return selected, current_depth, NavigationAction.BACK

        elif action == "quit":
            return [], current_depth, NavigationAction.QUIT


# ============================================================================
# Step 3: Configuration
# ============================================================================

def step_configuration(
    parsed: ParsedBook,
    config: RunConfig,
    chapters_dir: Path,
    console: Console,
) -> tuple[RunConfig, NavigationAction]:
    """Step 3: Configure generation settings."""
    # Calculate sections to skip
    gen_status = get_generation_status(chapters_dir, config.selected_indices)
    already_done = [idx for idx in config.selected_indices if gen_status.get(idx, False)]
    skip_count = len(already_done) if not config.force_regenerate else 0

    while True:
        console.clear()

        # Build config panel
        deck_display = config.deck_name or "Auto (Book::Part::Chapter)"
        max_cards_display = str(config.max_cards) if config.max_cards else "Unlimited"
        tags_display = ", ".join(config.tags) if config.tags else "(none)"

        config_lines = [
            f"  Output directory:    [cyan]{config.output_dir}[/]",
            f"  Model:               [cyan]{config.model}[/]",
            f"  Deck name:           [cyan]{deck_display}[/]",
            f"  Max cards/section:   [cyan]{max_cards_display}[/]",
            f"  Tags:                [cyan]{tags_display}[/]",
            "",
            "  " + "\u2500" * 55,
        ]

        if skip_count > 0:
            skip_check = "[x]" if not config.force_regenerate else "[ ]"
            force_check = "[x]" if config.force_regenerate else "[ ]"
            config_lines.append(f"  {skip_check} Skip already-generated sections ({skip_count} sections)")
            config_lines.append(f"  {force_check} Force regenerate all selected sections")

        console.print(Panel(
            "\n".join(config_lines),
            title="Generation Settings",
            border_style="green",
        ))
        console.print()
        console.print("[dim]Use \u2191\u2193 to navigate, Enter to edit, [C] Continue, [B] Back, [Q] Quit[/]")
        console.print()

        # Config options
        choices = [
            questionary.Choice(title=f"Output directory: {config.output_dir}", value="output_dir"),
            questionary.Choice(title=f"Model: {config.model}", value="model"),
            questionary.Choice(title=f"Deck name: {deck_display}", value="deck"),
            questionary.Choice(title=f"Max cards/section: {max_cards_display}", value="max_cards"),
            questionary.Choice(title=f"Tags: {tags_display}", value="tags"),
        ]

        if skip_count > 0:
            choices.append(questionary.Choice(
                title=f"{'[x]' if not config.force_regenerate else '[ ]'} Skip already-generated ({skip_count})",
                value="toggle_skip"
            ))

        choices.extend([
            questionary.Choice(title="[C] Continue", value="continue"),
            questionary.Choice(title="[B] Back", value="back"),
            questionary.Choice(title="[Q] Quit", value="quit"),
        ])

        result = questionary.select(
            "Edit settings:",
            choices=choices,
            style=WIZARD_STYLE,
            instruction="",
        ).ask()

        if result is None:
            return config, NavigationAction.QUIT

        if result == "output_dir":
            new_val = questionary.path(
                "Output directory:",
                default=str(config.output_dir),
                style=WIZARD_STYLE,
            ).ask()
            if new_val:
                config.output_dir = Path(new_val)

        elif result == "model":
            new_val = questionary.text(
                "Model:",
                default=config.model,
                style=WIZARD_STYLE,
            ).ask()
            if new_val:
                config.model = new_val

        elif result == "deck":
            new_val = questionary.text(
                "Deck name (leave empty for Auto):",
                default=config.deck_name or "",
                style=WIZARD_STYLE,
            ).ask()
            config.deck_name = new_val if new_val else None

        elif result == "max_cards":
            new_val = questionary.text(
                "Max cards per section (leave empty for Unlimited):",
                default=str(config.max_cards) if config.max_cards else "",
                style=WIZARD_STYLE,
            ).ask()
            if new_val and new_val.isdigit():
                config.max_cards = int(new_val)
            else:
                config.max_cards = None

        elif result == "tags":
            new_val = questionary.text(
                "Tags (comma-separated):",
                default=", ".join(config.tags),
                style=WIZARD_STYLE,
            ).ask()
            if new_val:
                config.tags = [t.strip() for t in new_val.split(",") if t.strip()]
            else:
                config.tags = []

        elif result == "toggle_skip":
            config.force_regenerate = not config.force_regenerate
            skip_count = 0 if config.force_regenerate else len(already_done)

        elif result == "continue":
            return config, NavigationAction.CONTINUE

        elif result == "back":
            return config, NavigationAction.BACK

        elif result == "quit":
            return config, NavigationAction.QUIT


# ============================================================================
# Step 4: Confirmation
# ============================================================================

def step_confirmation(
    parsed: ParsedBook,
    config: RunConfig,
    chapters_dir: Path,
    console: Console,
) -> NavigationAction:
    """Step 4: Display summary and confirm execution."""
    # Calculate stats
    gen_status = get_generation_status(chapters_dir, config.selected_indices)
    to_generate = [idx for idx in config.selected_indices if config.force_regenerate or not gen_status.get(idx, False)]
    to_skip = [idx for idx in config.selected_indices if not config.force_regenerate and gen_status.get(idx, False)]

    # Build deck name preview
    deck_preview = config.deck_name or f"Book::Part::Chapter (Level {config.depth_level})"

    # Output file path
    output_file = config.output_dir / "all_cards.txt"

    console.clear()

    summary_lines = [
        f"  Book:        [bold]{parsed.metadata.title}[/]",
        f"  Format:      {parsed.source_format.upper()}",
        "",
        f"  Sections:    {len(config.selected_indices)} selected",
        f"    \u2022 To generate: {len(to_generate)} sections",
        f"    \u2022 Skipping:    {len(to_skip)} sections (already done)",
        "",
        f"  Deck depth:  Level {config.depth_level}",
        f"  Output:      {output_file}",
        f"  Model:       {config.model}",
        f"  Max cards:   {config.max_cards or 'Unlimited'}",
        f"  Tags:        {', '.join(config.tags) if config.tags else '(none)'}",
    ]

    console.print(Panel(
        "\n".join(summary_lines),
        title="Summary",
        border_style="green",
    ))
    console.print()

    console.print(f"[dim]Estimated sections to process: {len(to_generate)}[/]")
    if to_generate:
        console.print("[dim]This will make API calls to Gemini for each section.[/]")
    console.print()

    result = questionary.select(
        "Ready to start?",
        choices=[
            questionary.Choice(title="[Enter] Start", value="start"),
            questionary.Choice(title="[B] Go Back", value="back"),
            questionary.Choice(title="[Q] Quit", value="quit"),
        ],
        style=WIZARD_STYLE,
        instruction="",
    ).ask()

    if result == "start":
        return NavigationAction.CONTINUE
    elif result == "back":
        return NavigationAction.BACK
    else:
        return NavigationAction.QUIT


# ============================================================================
# Step 5: Execution
# ============================================================================

def step_execution(
    book_path: Path,
    parsed: ParsedBook,
    config: RunConfig,
    chapters_dir: Path,
    console: Console,
) -> None:
    """Step 5: Execute the full pipeline."""
    console.clear()
    console.print(f"[bold]Processing:[/] {parsed.metadata.title}")
    console.print()

    # Step 1: Parse (if needed)
    console.print("[bold cyan][1/3][/] Parsing...")

    if not chapters_dir.exists():
        # Need to parse first
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Extracting sections...", total=None)

            writer = OutputWriter(chapters_dir, book_path)
            chapter_metadata = []

            for idx in config.selected_indices:
                chapter = parsed.chapters[idx]
                _, metadata = writer.write_chapter(chapter, "markdown")
                chapter_metadata.append(metadata)

            # Write manifest
            writer.write_manifest(parsed, config.selected_indices, chapter_metadata)

        console.print(f"  [green]\u2713[/] Extracted {len(config.selected_indices)} sections to {chapters_dir}/")
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
            chapter_metadata = []

            for idx in new_indices:
                chapter = parsed.chapters[idx]
                _, metadata = writer.write_chapter(chapter, "markdown")
                chapter_metadata.append(metadata)

            console.print(f"  [green]\u2713[/] Extracted {len(new_indices)} new sections")
        else:
            console.print(f"  [green]\u2713[/] Using existing sections in {chapters_dir}/")

    console.print()

    # Step 2: Generate
    console.print("[bold cyan][2/3][/] Generating flashcards...")

    gen_status = get_generation_status(chapters_dir, config.selected_indices)
    to_generate = [idx for idx in config.selected_indices
                   if config.force_regenerate or not gen_status.get(idx, False)]

    if not to_generate:
        console.print("  [green]\u2713[/] All sections already generated")
    else:
        # Call execute_generate for the actual generation
        execute_generate(
            chapters_dir=chapters_dir,
            max_cards=config.max_cards,
            model=config.model,
            dry_run=False,
            quiet=False,
            console=console,
            chapters=",".join(str(idx + 1) for idx in to_generate),
            deck=config.deck_name,
            tags=config.tags or None,
            force=config.force_regenerate,
        )

    console.print()

    # Step 3: Export
    console.print("[bold cyan][3/3][/] Exporting...")

    output_file = config.output_dir / "all_cards.txt"
    execute_export(
        chapters_dir=chapters_dir,
        output_file=output_file,
        console=console,
        quiet=True,
    )

    console.print(f"  [green]\u2713[/] Exported to {output_file}")
    console.print()

    # Final summary
    from anki_gen.commands.export import find_card_files, parse_card_file, calculate_stats

    card_files = find_card_files(chapters_dir)
    chapters_data = []
    for path in card_files:
        parsed_cards = parse_card_file(path)
        if parsed_cards:
            chapters_data.append(parsed_cards)

    if chapters_data:
        stats = calculate_stats(chapters_data)

        summary_lines = [
            f"  Total cards in export: {stats.total_cards} ({stats.basic_count} basic, {stats.cloze_count} cloze)",
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


# ============================================================================
# Main Wizard
# ============================================================================

def execute_run(
    book_path: Path | None,
    non_interactive: bool,
    force: bool,
    console: Console,
) -> None:
    """Execute the interactive run wizard."""
    config = RunConfig(force_regenerate=force)
    parsed: ParsedBook | None = None
    chapters_dir: Path | None = None

    current_step = WizardStep.FILE_SELECTION

    while True:
        if current_step == WizardStep.FILE_SELECTION:
            # Step 1: File Selection
            selected_path, action = step_file_selection(book_path, console)

            if action == NavigationAction.QUIT or selected_path is None:
                console.print("[dim]Goodbye![/]")
                return

            book_path = selected_path

            # Parse the book
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

            chapters_dir = get_default_output_dir(book_path)
            config.output_dir = chapters_dir

            if non_interactive:
                # Non-interactive mode: select all, use defaults
                config.selected_indices = list(range(len(parsed.chapters)))
                config.depth_level = get_max_depth(build_section_tree(parsed, chapters_dir))
                # Skip directly to execution
                step_execution(book_path, parsed, config, chapters_dir, console)
                return

            current_step = WizardStep.SECTION_SELECTION

        elif current_step == WizardStep.SECTION_SELECTION:
            # Step 2: Section Selection
            if parsed is None:
                current_step = WizardStep.FILE_SELECTION
                continue

            selected, depth, action = step_section_selection(
                parsed, chapters_dir, console, config
            )

            if action == NavigationAction.QUIT:
                console.print("[dim]Goodbye![/]")
                return
            elif action == NavigationAction.BACK:
                config.selected_indices = selected
                config.depth_level = depth
                current_step = WizardStep.FILE_SELECTION
                book_path = None  # Allow re-selection
            else:
                config.selected_indices = selected
                config.depth_level = depth
                current_step = WizardStep.CONFIGURATION

        elif current_step == WizardStep.CONFIGURATION:
            # Step 3: Configuration
            if parsed is None:
                current_step = WizardStep.FILE_SELECTION
                continue

            config, action = step_configuration(parsed, config, chapters_dir, console)

            if action == NavigationAction.QUIT:
                console.print("[dim]Goodbye![/]")
                return
            elif action == NavigationAction.BACK:
                current_step = WizardStep.SECTION_SELECTION
            else:
                current_step = WizardStep.CONFIRMATION

        elif current_step == WizardStep.CONFIRMATION:
            # Step 4: Confirmation
            if parsed is None:
                current_step = WizardStep.FILE_SELECTION
                continue

            action = step_confirmation(parsed, config, chapters_dir, console)

            if action == NavigationAction.QUIT:
                console.print("[dim]Goodbye![/]")
                return
            elif action == NavigationAction.BACK:
                current_step = WizardStep.CONFIGURATION
            else:
                current_step = WizardStep.EXECUTION

        elif current_step == WizardStep.EXECUTION:
            # Step 5: Execution
            if parsed is None or book_path is None:
                current_step = WizardStep.FILE_SELECTION
                continue

            step_execution(book_path, parsed, config, chapters_dir, console)
            return
