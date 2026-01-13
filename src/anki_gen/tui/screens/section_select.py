"""Screen 2: Section Selection."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.coordinate import Coordinate
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static


class SectionSelectScreen(Screen):
    """Screen for selecting sections to process."""

    BINDINGS = [
        Binding("space", "toggle_selection", "Toggle", show=True, priority=True),
        Binding("a", "select_all", "All", show=True),
        Binding("n", "select_none", "None", show=True),
        Binding("d", "cycle_depth", "Depth", show=True),
        Binding("enter", "continue", "Continue", show=True, priority=True),
        Binding("b", "go_back", "Back", show=True),
        Binding("escape", "go_back", "Back", show=False),
        Binding("q", "quit", "Quit", show=False),  # Hide from footer - redundant
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._mounted = False
        self._current_depth = 1

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()
        with Container(id="main"):
            yield Static(id="book-info")
            yield Static(id="depth-indicator")
            yield DataTable(id="section-table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the section table when mounted."""
        state = self.app.state

        # Set up book info panel
        self._update_book_info()

        # Set up table columns
        table = self.query_one("#section-table", DataTable)
        table.add_column("", key="checkbox", width=5)
        table.add_column("Section", key="section")
        table.add_column("Words", key="words", width=10)
        table.add_column("Status", key="status", width=12)
        table.cursor_type = "row"
        table.zebra_stripes = True

        # Initialize depth level from state (without triggering refresh yet)
        self._current_depth = state.config.depth_level or 1

        # Mark as mounted and populate the table
        self._mounted = True
        self._populate_table()

        # Update depth indicator
        self._update_depth_indicator()

    def _update_book_info(self) -> None:
        """Update the book info panel."""
        state = self.app.state
        parsed = state.parsed_book

        if not parsed:
            return

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

        has_hierarchy = state.max_depth > 1
        depth_info = f" ({state.max_depth} levels deep)" if has_hierarchy else ""
        info_lines.append(f"[dim]Total Sections:[/] {len(parsed.chapters)}{depth_info}")

        self.query_one("#book-info", Static).update("\n".join(info_lines))

    def _update_depth_indicator(self) -> None:
        """Update the depth level indicator."""
        state = self.app.state
        has_hierarchy = state.max_depth > 1

        if has_hierarchy:
            next_depth = (self._current_depth % state.max_depth) + 1
            text = f"[cyan]Section View: Level {self._current_depth} of {state.max_depth}[/]  [dim](Press D to switch to Level {next_depth})[/]"
        else:
            text = ""

        self.query_one("#depth-indicator", Static).update(text)

    def _get_visible_nodes(self):
        """Get the currently visible nodes."""
        from anki_gen.tui.state import flatten_to_depth

        state = self.app.state
        if not state.section_tree:
            return []
        return flatten_to_depth(state.section_tree, self._current_depth)

    def _populate_table(self) -> None:
        """Populate the section table with current data."""
        from anki_gen.tui.state import (
            calculate_aggregated_word_count,
            get_checkbox_state,
            get_status_display,
        )

        if not self._mounted:
            return

        state = self.app.state
        if not state.section_tree:
            return

        table = self.query_one("#section-table", DataTable)

        # Guard: don't try to add rows if columns haven't been set up yet
        if not table.columns:
            return

        # Save current cursor position and scroll position
        saved_cursor_row = table.cursor_row
        saved_scroll_y = table.scroll_y

        # Clear and repopulate
        table.clear()

        visible_nodes = self._get_visible_nodes()

        for idx, node in enumerate(visible_nodes):
            checkbox = get_checkbox_state(node)

            # Color the checkbox based on state - use Text with style (not markup, as [x] looks like markup)
            if checkbox == "[x]":
                checkbox_display = Text(checkbox, style="green")
            elif checkbox == "[~]":
                checkbox_display = Text(checkbox, style="yellow")
            else:
                checkbox_display = Text(checkbox, style="dim")

            # Indentation based on level
            indent = "  " * node.level
            if node.children and node.level < self._current_depth - 1:
                prefix = f"{indent}├─ "
            elif node.level > 0:
                prefix = f"{indent}└─ "
            else:
                prefix = ""

            title_display = f"{prefix}{node.title}"
            if len(title_display) > 50:
                title_display = title_display[:47] + "..."

            word_count = calculate_aggregated_word_count(node)
            status_text, status_class = get_status_display(node)

            # Color the status - use Text for proper rendering
            if status_class == "status-done":
                status_display = Text.from_markup(f"[green]{status_text}[/]")
            elif status_class == "status-partial":
                status_display = Text.from_markup(f"[yellow]{status_text}[/]")
            else:
                status_display = Text.from_markup(f"[dim]{status_text}[/]")

            # Add row with a key for stable reference
            table.add_row(
                checkbox_display,
                title_display,
                f"{word_count:,}",
                status_display,
                key=str(node.index),
            )

        # Restore cursor position (clamped to valid range) without scrolling
        if saved_cursor_row is not None and len(visible_nodes) > 0:
            new_row = min(saved_cursor_row, len(visible_nodes) - 1)
            # Set cursor without triggering scroll by restoring scroll position after
            table.cursor_coordinate = Coordinate(new_row, 0)
            # Restore scroll position to prevent auto-scroll on selection
            table.scroll_y = saved_scroll_y

    def _update_row(self, row_index: int) -> None:
        """Update a single row in the table without clearing everything."""
        from anki_gen.tui.state import (
            calculate_aggregated_word_count,
            get_checkbox_state,
            get_status_display,
        )

        visible_nodes = self._get_visible_nodes()
        if row_index >= len(visible_nodes):
            return

        node = visible_nodes[row_index]
        table = self.query_one("#section-table", DataTable)

        checkbox = get_checkbox_state(node)
        if checkbox == "[x]":
            checkbox_display = Text(checkbox, style="green")
        elif checkbox == "[~]":
            checkbox_display = Text(checkbox, style="yellow")
        else:
            checkbox_display = Text(checkbox, style="dim")

        # Indentation based on level
        indent = "  " * node.level
        if node.children and node.level < self._current_depth - 1:
            prefix = f"{indent}├─ "
        elif node.level > 0:
            prefix = f"{indent}└─ "
        else:
            prefix = ""

        title_display = f"{prefix}{node.title}"
        if len(title_display) > 50:
            title_display = title_display[:47] + "..."

        word_count = calculate_aggregated_word_count(node)
        status_text, status_class = get_status_display(node)

        if status_class == "status-done":
            status_display = Text.from_markup(f"[green]{status_text}[/]")
        elif status_class == "status-partial":
            status_display = Text.from_markup(f"[yellow]{status_text}[/]")
        else:
            status_display = Text.from_markup(f"[dim]{status_text}[/]")

        # Update the row using its key
        row_key = str(node.index)
        try:
            table.update_cell(row_key, "checkbox", checkbox_display)
            table.update_cell(row_key, "section", title_display)
            table.update_cell(row_key, "words", f"{word_count:,}")
            table.update_cell(row_key, "status", status_display)
        except Exception:
            # If update fails, fall back to full refresh
            self._populate_table()

    def action_toggle_selection(self) -> None:
        """Toggle selection of current row."""
        from anki_gen.tui.state import propagate_selection_down, propagate_selection_up

        table = self.query_one("#section-table", DataTable)
        row_index = table.cursor_row

        visible_nodes = self._get_visible_nodes()
        if row_index is not None and row_index < len(visible_nodes):
            node = visible_nodes[row_index]
            new_state = not node.selected
            propagate_selection_down(node, new_state)
            propagate_selection_up(node)

            # Update just this row and any parent rows that might have changed
            # For simplicity, refresh the whole table but preserve cursor
            self._populate_table()

    def action_select_all(self) -> None:
        """Select all sections."""
        from anki_gen.tui.state import propagate_selection_down

        state = self.app.state
        if state.section_tree:
            for root in state.section_tree:
                propagate_selection_down(root, True)
            self._populate_table()

    def action_select_none(self) -> None:
        """Deselect all sections."""
        from anki_gen.tui.state import propagate_selection_down

        state = self.app.state
        if state.section_tree:
            for root in state.section_tree:
                propagate_selection_down(root, False)
            self._populate_table()

    def action_cycle_depth(self) -> None:
        """Cycle through depth levels."""
        state = self.app.state
        if state.max_depth > 1:
            self._current_depth = (self._current_depth % state.max_depth) + 1
            state.config.depth_level = self._current_depth
            self._populate_table()
            self._update_depth_indicator()

    def action_continue(self) -> None:
        """Continue to configuration screen."""
        from anki_gen.tui.screens.config import ConfigScreen
        from anki_gen.tui.state import get_selected_leaf_indices

        state = self.app.state
        if not state.section_tree:
            return

        selected = get_selected_leaf_indices(state.section_tree)
        if not selected:
            self.notify("Please select at least one section.", severity="warning")
            return

        # Save selected indices to state
        state.config.selected_indices = selected
        state.config.depth_level = self._current_depth

        # Navigate to config screen
        self.app.push_screen(ConfigScreen())

    def action_go_back(self) -> None:
        """Go back to file selection."""
        from anki_gen.tui.screens.file_select import FileSelectScreen
        from anki_gen.tui.state import get_selected_leaf_indices

        # Save current selections before going back
        state = self.app.state
        if state.section_tree:
            state.config.selected_indices = get_selected_leaf_indices(state.section_tree)
            state.config.depth_level = self._current_depth

        # Pop this screen and go to file select
        self.app.pop_screen()
        # Clear state for new file selection
        state.book_path = None
        state.parsed_book = None
        state.section_tree = None
        self.app.push_screen(FileSelectScreen())

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit(0)
