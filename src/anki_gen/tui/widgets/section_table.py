"""Custom section table widget."""

from __future__ import annotations

from textual.widgets import DataTable


class SectionTable(DataTable):
    """Custom DataTable for section selection with checkbox support."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cursor_type = "row"
