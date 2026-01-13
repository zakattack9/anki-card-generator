"""Screen 1: File Selection."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static


class FileSelectScreen(Screen):
    """Screen for selecting a book file to process."""

    BINDINGS = [
        Binding("enter", "select_file", "Select", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("escape", "quit", "Quit", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.books: list[Path] = []

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()
        with Container(id="main"):
            yield Static("Select a book to process:", id="prompt")
            yield DataTable(id="file-table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the file table when mounted."""
        from anki_gen.tui.pipeline import format_file_size, scan_for_books

        self.books = scan_for_books(Path("."))

        table = self.query_one("#file-table", DataTable)
        table.add_columns("File", "Size")
        table.cursor_type = "row"

        if not self.books:
            # No books found - show message
            self.query_one("#prompt", Static).update(
                "[red]No PDF or EPUB files found in current directory.[/]\n"
                "[dim]Supported formats: .pdf, .epub[/]"
            )
            table.display = False
        else:
            for book in self.books:
                size = format_file_size(book.stat().st_size)
                table.add_row(book.name, size)

    def action_select_file(self) -> None:
        """Select the currently highlighted file."""
        if not self.books:
            self.app.exit(1)
            return

        table = self.query_one("#file-table", DataTable)
        row_key = table.cursor_row

        if row_key is not None and row_key < len(self.books):
            selected_book = self.books[row_key]
            self._load_book(selected_book)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle double-click or enter on a row."""
        table = self.query_one("#file-table", DataTable)
        row_index = table.cursor_row
        if row_index is not None and row_index < len(self.books):
            selected_book = self.books[row_index]
            self._load_book(selected_book)

    def _load_book(self, book_path: Path) -> None:
        """Load and parse the selected book."""
        from anki_gen.tui.screens.section_select import SectionSelectScreen

        # Parse the book
        self.app._parse_book(book_path)

        # Navigate to section selection
        self.app.push_screen(SectionSelectScreen())

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit(0)
