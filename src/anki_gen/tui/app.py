"""Main Textual application for the run wizard."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

from anki_gen.tui.state import WizardState

if TYPE_CHECKING:
    from anki_gen.models.book import ParsedBook


class RunWizardApp(App):
    """Main application for the run wizard."""

    CSS_PATH = "styles.tcss"
    TITLE = "anki-gen run"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(
        self,
        book_path: Path | None = None,
        force: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.theme = "monokai"
        self.initial_book_path = book_path
        self.state = WizardState()
        self.state.config.force_regenerate = force

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()
        yield Footer()

    def on_mount(self) -> None:
        """Start the wizard on the appropriate screen."""
        from anki_gen.tui.screens import FileSelectScreen, SectionSelectScreen

        if self.initial_book_path:
            # Validate and parse the book first
            if not self.initial_book_path.exists():
                self.notify(
                    f"File not found: {self.initial_book_path}",
                    severity="error",
                )
                self.exit(1)
                return

            from anki_gen.core.parser_factory import ParserFactory

            if not ParserFactory.is_supported(self.initial_book_path):
                self.notify(
                    f"Unsupported file format: {self.initial_book_path.suffix}",
                    severity="error",
                )
                self.exit(1)
                return

            # Parse the book
            self._parse_book(self.initial_book_path)

            # Skip file selection, go directly to section selection
            self.push_screen(SectionSelectScreen())
        else:
            self.push_screen(FileSelectScreen())

    def _parse_book(self, book_path: Path) -> None:
        """Parse a book and update state."""
        from anki_gen.cache.manager import CacheManager
        from anki_gen.core.parser_factory import ParserFactory
        from anki_gen.tui.pipeline import (
            check_book_hash_changed,
            get_default_chapters_dir,
        )
        from anki_gen.tui.state import build_section_tree, get_max_depth

        self.state.book_path = book_path

        cache_manager = CacheManager(book_path.parent)
        cached = cache_manager.get_cached_structure(book_path)

        parser = ParserFactory.create(book_path)
        self.state.parsed_book = parser.parse()

        if not cached:
            cache_manager.save_structure(book_path, self.state.parsed_book)

        # Set chapters_dir
        self.state.config.chapters_dir = get_default_chapters_dir(book_path)

        # Build section tree
        self.state.section_tree = build_section_tree(
            self.state.parsed_book, self.state.config.chapters_dir
        )
        self.state.max_depth = get_max_depth(self.state.section_tree)

        # Check if book file has changed
        hash_changed, warning_msg = check_book_hash_changed(
            book_path, self.state.config.chapters_dir
        )
        if hash_changed and warning_msg:
            self.state.config.force_regenerate = True
            self.notify(warning_msg, severity="warning", timeout=5)

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit(0)
