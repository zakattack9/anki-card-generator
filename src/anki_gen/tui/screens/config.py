"""Screen 3: Configuration."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Checkbox, Footer, Header, Input, Label, Rule, Static


class ConfigScreen(Screen):
    """Screen for configuring generation settings."""

    BINDINGS = [
        Binding("tab", "focus_next", "Next Field", show=False),
        Binding("shift+tab", "focus_previous", "Prev Field", show=False),
        Binding("s", "toggle_skip", "Toggle Skip", show=True, priority=True),
        Binding("enter", "continue", "Continue", show=True),
        Binding("b", "go_back", "Back", show=True),
        Binding("escape", "go_back", "Back", show=False),
        Binding("q", "quit", "Quit", show=True),
    ]

    skip_regenerate = reactive(True)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.already_done: list[int] = []

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()
        with Container(id="main"):
            yield Static("[bold]Generation Settings[/]", id="config-title")
            with Container(id="config-panel"):
                with Vertical():
                    with Horizontal(classes="config-row"):
                        yield Label("Output directory:", classes="config-label")
                        yield Input(
                            placeholder="./",
                            id="output-dir",
                            classes="config-value",
                        )
                    with Horizontal(classes="config-row"):
                        yield Label("Model:", classes="config-label")
                        yield Input(
                            value="gemini-3-pro-preview",
                            id="model",
                            classes="config-value",
                        )
                    with Horizontal(classes="config-row"):
                        yield Label("Deck name:", classes="config-label")
                        yield Input(
                            placeholder="Auto",
                            id="deck-name",
                            classes="config-value",
                        )
                    with Horizontal(classes="config-row"):
                        yield Label("Max cards/section:", classes="config-label")
                        yield Input(
                            placeholder="Unlimited",
                            id="max-cards",
                            classes="config-value",
                        )
                    with Horizontal(classes="config-row"):
                        yield Label("Tags:", classes="config-label")
                        yield Input(
                            placeholder="(none)",
                            id="tags",
                            classes="config-value",
                        )
                    yield Rule()
                    with Horizontal(classes="checkbox-row", id="skip-row"):
                        yield Checkbox("", id="skip-toggle", value=True)
                        yield Static("Skip already-generated sections", id="skip-label")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize form with current config values."""
        from anki_gen.tui.pipeline import get_deck_hierarchy_preview, get_generation_status

        state = self.app.state
        config = state.config

        # Calculate sections to skip
        if config.chapters_dir:
            gen_status = get_generation_status(
                config.chapters_dir, config.selected_indices
            )
            self.already_done = [
                idx for idx in config.selected_indices if gen_status.get(idx, False)
            ]
        else:
            self.already_done = []

        # Set initial values
        self.query_one("#output-dir", Input).value = str(config.output_dir)
        self.query_one("#model", Input).value = config.model
        self.query_one("#deck-name", Input).value = config.deck_name or ""

        # Show deck hierarchy preview in placeholder
        hierarchy_preview = get_deck_hierarchy_preview(config.depth_level)
        self.query_one("#deck-name", Input).placeholder = f"Auto ({hierarchy_preview})"

        self.query_one("#max-cards", Input).value = (
            str(config.max_cards) if config.max_cards else ""
        )
        self.query_one("#tags", Input).value = ", ".join(config.tags)

        # Set up skip toggle
        self.skip_regenerate = not config.force_regenerate
        skip_toggle = self.query_one("#skip-toggle", Checkbox)
        skip_toggle.value = self.skip_regenerate

        # Update skip label and visibility
        self._update_skip_display()

    def _update_skip_display(self) -> None:
        """Update the skip toggle label and visibility."""
        skip_row = self.query_one("#skip-row")
        skip_label = self.query_one("#skip-label", Static)

        if self.already_done:
            skip_row.display = True
            count = len(self.already_done)
            if self.skip_regenerate:
                skip_label.update(f"Skip already-generated sections ({count} sections)")
            else:
                skip_label.update(f"Force regenerate all selected sections ({count} to regenerate)")
        else:
            skip_row.display = False

    def watch_skip_regenerate(self, new_value: bool) -> None:
        """React to skip toggle changes."""
        self._update_skip_display()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox changes."""
        if event.checkbox.id == "skip-toggle":
            self.skip_regenerate = event.value

    def action_toggle_skip(self) -> None:
        """Toggle the skip regenerate setting."""
        if self.already_done:
            skip_toggle = self.query_one("#skip-toggle", Checkbox)
            skip_toggle.value = not skip_toggle.value

    def action_continue(self) -> None:
        """Continue to confirmation screen."""
        from pathlib import Path

        from anki_gen.tui.screens.confirm import ConfirmScreen

        state = self.app.state
        config = state.config

        # Save form values to config
        output_dir = self.query_one("#output-dir", Input).value.strip()
        config.output_dir = Path(output_dir) if output_dir else Path(".")

        config.model = self.query_one("#model", Input).value.strip() or "gemini-3-pro-preview"

        deck_name = self.query_one("#deck-name", Input).value.strip()
        config.deck_name = deck_name if deck_name else None

        max_cards = self.query_one("#max-cards", Input).value.strip()
        config.max_cards = int(max_cards) if max_cards.isdigit() else None

        tags = self.query_one("#tags", Input).value.strip()
        config.tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        config.force_regenerate = not self.skip_regenerate

        # Navigate to confirmation screen
        self.app.push_screen(ConfirmScreen())

    def action_go_back(self) -> None:
        """Go back to section selection."""
        self.app.pop_screen()

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit(0)
