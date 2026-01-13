"""State management for the run wizard TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from anki_gen.models.book import ParsedBook


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
    chapters_dir: Path | None = None
    model: str = "gemini-3-pro-preview"
    deck_name: str | None = None  # None = auto
    max_cards: int | None = None  # None = unlimited
    tags: list[str] = field(default_factory=list)
    force_regenerate: bool = False
    selected_indices: list[int] = field(default_factory=list)
    depth_level: int = 1


@dataclass
class WizardState:
    """Shared state across all screens."""

    book_path: Path | None = None
    parsed_book: "ParsedBook | None" = None
    section_tree: list[SectionNode] | None = None
    config: RunConfig = field(default_factory=RunConfig)

    # Selection state
    selected_indices: set[int] = field(default_factory=set)
    depth_level: int = 1
    max_depth: int = 1

    # Execution results
    generated_count: int = 0
    exported_count: int = 0
    newly_generated_cards: int = 0
    previously_generated_cards: int = 0


# ============================================================================
# Helper functions for section tree operations
# ============================================================================


def build_section_tree(
    parsed: "ParsedBook", chapters_dir: Path | None
) -> list[SectionNode]:
    """Build hierarchical section tree with status info."""
    from anki_gen.tui.pipeline import get_generation_status

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


def find_node_by_index(nodes: list[SectionNode], index: int) -> SectionNode | None:
    """Find a node in the tree by its chapter index."""
    for node in nodes:
        if node.index == index:
            return node
        found = find_node_by_index(node.children, index)
        if found:
            return found
    return None


def get_ancestors_to_depth(node: SectionNode, depth_level: int) -> list[str]:
    """Get ancestor titles up to the specified depth level."""
    ancestors: list[str] = []

    current: SectionNode | None = node
    while current:
        ancestors.append(current.title)
        current = current.parent

    ancestors.reverse()
    return ancestors[:depth_level]


def calculate_deck_name_for_chapter(
    chapter_index: int,
    section_tree: list[SectionNode],
    depth_level: int,
    book_title: str,
) -> str:
    """Calculate the deck name for a chapter based on depth level and hierarchy."""
    clean_book = book_title.strip()

    node = find_node_by_index(section_tree, chapter_index)
    if node is None:
        return clean_book

    ancestors = get_ancestors_to_depth(node, depth_level)
    parts = [clean_book] + ancestors
    return "::".join(parts)


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
    selected_count = sum(
        1 for c in node.children if c.selected or get_partial_selection(c)
    )
    if selected_count == 0:
        return "[ ]"
    elif selected_count == len(node.children) and all(
        get_checkbox_state(c) == "[x]" for c in node.children
    ):
        return "[x]"
    else:
        return "[~]"


def get_partial_selection(node: SectionNode) -> bool:
    """Check if node has partial selection."""
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


def get_status_display(node: SectionNode) -> tuple[str, str]:
    """Get status column display and style class for a node."""
    if node.status == "done":
        return "\u2713 Done", "status-done"
    elif node.status == "partial":

        def count_done_leaves(n: SectionNode) -> tuple[int, int]:
            if not n.children:
                return (1 if n.status == "done" else 0, 1)
            done = 0
            total = 0
            for child in n.children:
                d, t = count_done_leaves(child)
                done += d
                total += t
            return done, total

        done, total = count_done_leaves(node)
        return f"{done}/{total} done", "status-partial"
    else:
        return "Pending", "status-pending"


def propagate_selection_down(node: SectionNode, selected: bool) -> None:
    """Propagate selection state to all children."""
    node.selected = selected
    for child in node.children:
        propagate_selection_down(child, selected)


def propagate_selection_up(node: SectionNode) -> None:
    """Update parent selection based on children state."""
    if node.parent:
        all_selected = all(
            c.selected and not get_partial_selection(c) for c in node.parent.children
        )
        none_selected = all(
            not c.selected and not get_partial_selection(c) for c in node.parent.children
        )

        if all_selected:
            node.parent.selected = True
        elif none_selected:
            node.parent.selected = False

        propagate_selection_up(node.parent)
