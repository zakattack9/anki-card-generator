"""Error dialog modal screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ErrorDialog(ModalScreen[str]):
    """Modal dialog for displaying errors with options."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=False),
    ]

    def __init__(
        self,
        title: str,
        message: str,
        options: list[tuple[str, str]] | None = None,
        **kwargs,
    ) -> None:
        """Initialize the error dialog.

        Args:
            title: Dialog title
            message: Error message to display
            options: List of (key, label) tuples for action buttons
        """
        super().__init__(**kwargs)
        self.dialog_title = title
        self.message = message
        self.options = options or [("q", "Quit")]

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        with Container(id="error-dialog"):
            yield Static(f"[bold red]{self.dialog_title}[/]", id="error-title")
            yield Static(self.message, id="error-message")
            with Horizontal(id="error-actions"):
                for key, label in self.options:
                    yield Button(f"[{key.upper()}] {label}", id=f"btn-{key}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        if button_id and button_id.startswith("btn-"):
            key = button_id[4:]  # Remove "btn-" prefix
            self.dismiss(key)

    def action_dismiss(self) -> None:
        """Dismiss the dialog."""
        self.dismiss("dismiss")
