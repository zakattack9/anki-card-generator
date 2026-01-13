"""Screen 4: Confirmation."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


class ConfirmScreen(Screen):
    """Screen for confirming execution."""

    BINDINGS = [
        Binding("enter", "start_execution", "Start", show=True),
        Binding("e", "export_only", "Export Only", show=False),
        Binding("r", "regenerate_all", "Regenerate", show=False),
        Binding("b", "go_back", "Back", show=True),
        Binding("escape", "go_back", "Back", show=False),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.to_generate: list[int] = []
        self.to_skip: list[int] = []
        self.all_sections_done = False

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()
        with Container(id="main"):
            yield Static(id="summary-panel")
            yield Static(id="warnings")
            yield Static(id="help-text", classes="instruction")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the confirmation summary."""
        from anki_gen.tui.pipeline import (
            LARGE_BOOK_THRESHOLD,
            get_deck_hierarchy_preview,
            get_generation_status,
        )

        state = self.app.state
        config = state.config
        parsed = state.parsed_book

        if not parsed or not config.chapters_dir:
            return

        # Calculate stats
        gen_status = get_generation_status(
            config.chapters_dir, config.selected_indices
        )
        self.to_generate = [
            idx
            for idx in config.selected_indices
            if config.force_regenerate or not gen_status.get(idx, False)
        ]
        self.to_skip = [
            idx
            for idx in config.selected_indices
            if not config.force_regenerate and gen_status.get(idx, False)
        ]
        self.all_sections_done = len(self.to_generate) == 0 and len(self.to_skip) > 0

        # Output file path
        output_file = config.output_dir / "all_cards.txt"

        # Format line with extraction method for PDF
        if parsed.source_format == "pdf":
            method_display = parsed.extraction_method.value.replace("_", " ").title()
            format_display = f"{parsed.source_format.upper()} ({method_display})"
        else:
            format_display = parsed.source_format.upper()

        # Build deck hierarchy preview
        hierarchy_preview = get_deck_hierarchy_preview(config.depth_level)
        deck_display = config.deck_name or f"Auto ({hierarchy_preview})"

        # Build summary
        summary_lines = [
            "[bold]Summary[/]",
            "",
            f"  Book:        [bold]{parsed.metadata.title}[/]",
            f"  Format:      {format_display}",
            "",
            f"  Sections:    {len(config.selected_indices)} selected",
            f"    \u2022 To generate: {len(self.to_generate)} sections (at lowest level)",
            f"    \u2022 Skipping:    {len(self.to_skip)} sections (already done)",
            "",
            f"  Deck depth:  Level {config.depth_level} ({hierarchy_preview})",
            f"  Deck name:   {deck_display}",
            f"  Output:      {output_file}",
            f"  Model:       {config.model}",
            f"  Max cards:   {config.max_cards or 'Unlimited'}",
            f"  Tags:        {', '.join(config.tags) if config.tags else '(none)'}",
        ]

        self.query_one("#summary-panel", Static).update("\n".join(summary_lines))

        # Build warnings
        warning_lines = []
        if len(self.to_generate) >= LARGE_BOOK_THRESHOLD:
            warning_lines.append(
                f"[yellow]\u26a0 Large book: {len(self.to_generate)} sections "
                "will require many API calls[/]"
            )

        if self.to_generate:
            warning_lines.append("")
            warning_lines.append(f"[dim]Estimated sections to process: {len(self.to_generate)}[/]")
            warning_lines.append("[dim]This will make API calls to Gemini for each section.[/]")
        elif self.all_sections_done:
            warning_lines.append("")
            warning_lines.append("[green]All selected sections are already generated![/]")

        self.query_one("#warnings", Static).update("\n".join(warning_lines))

        # Update help text based on state
        self._update_help_text()

    def _update_help_text(self) -> None:
        """Update the help text based on current state."""
        if self.all_sections_done:
            help_text = "[E] Re-export only  [R] Regenerate anyway  [B] Back  [Q] Quit"
        else:
            help_text = "[Enter] Start  [B] Back  [Q] Quit"
        self.query_one("#help-text", Static).update(f"[dim]{help_text}[/]")

    def action_start_execution(self) -> None:
        """Start the execution."""
        from anki_gen.tui.screens.execute import ExecuteScreen

        self.app.push_screen(ExecuteScreen())

    def action_export_only(self) -> None:
        """Skip generation, just re-export existing cards."""
        if self.all_sections_done:
            from anki_gen.tui.screens.execute import ExecuteScreen

            # Don't force regenerate
            self.app.state.config.force_regenerate = False
            self.app.push_screen(ExecuteScreen())

    def action_regenerate_all(self) -> None:
        """Force regenerate all sections."""
        if self.all_sections_done:
            from anki_gen.tui.screens.execute import ExecuteScreen

            self.app.state.config.force_regenerate = True
            self.app.push_screen(ExecuteScreen())

    def action_go_back(self) -> None:
        """Go back to configuration."""
        self.app.pop_screen()

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit(0)
