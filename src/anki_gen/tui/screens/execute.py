"""Screen 5: Execution."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Footer, Header, ProgressBar, Static


class ExecuteScreen(Screen):
    """Screen for executing the pipeline."""

    BINDINGS = [
        Binding("enter", "finish", "Done", show=False),
        Binding("q", "quit", "Quit", show=False),
        Binding("ctrl+c", "interrupt", "Cancel", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.interrupted = False
        self.completed = False
        self.aborted = False
        self.newly_generated_count = 0
        self.to_generate: list[int] = []
        self.previously_generated: list[int] = []
        self.skipped_sections: list[int] = []

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()
        with Container(id="main"):
            yield Static(id="title")
            yield Static(id="step-1")
            yield Static(id="step-2")
            yield ProgressBar(id="generation-progress", total=100, show_eta=False)
            yield Static(id="current-section")
            yield Static(id="step-3")
            yield Static(id="completion-panel")
            yield Static(id="help-text", classes="instruction")
        yield Footer()

    async def on_mount(self) -> None:
        """Start the pipeline when mounted."""
        state = self.app.state
        parsed = state.parsed_book

        if not parsed:
            return

        # Set title
        self.query_one("#title", Static).update(
            f"[bold]Processing:[/] {parsed.metadata.title}\n"
        )

        # Hide progress bar and completion panel initially
        self.query_one("#generation-progress", ProgressBar).display = False
        self.query_one("#completion-panel", Static).display = False
        self.query_one("#current-section", Static).display = False

        # Run the pipeline
        await self._run_pipeline()

    async def _run_pipeline(self) -> None:
        """Run the complete pipeline."""
        from anki_gen.tui.pipeline import (
            InterruptedError,
            get_generation_status,
            run_export_step,
            run_parse_step,
            validate_output_dir,
        )
        from anki_gen.tui.state import build_section_tree
        from anki_gen.tui.widgets.error_dialog import ErrorDialog

        state = self.app.state
        config = state.config
        parsed = state.parsed_book
        book_path = state.book_path

        if not parsed or not book_path or not config.chapters_dir:
            return

        chapters_dir = config.chapters_dir

        # Validate output directory
        config.output_dir, warning = validate_output_dir(config.output_dir)
        if warning:
            self.notify(warning, severity="warning")

        try:
            # Step 1: Parse
            self.query_one("#step-1", Static).update("[bold cyan][1/3][/] Parsing...")

            try:
                extracted_count = await run_parse_step(
                    book_path,
                    parsed,
                    config,
                    chapters_dir,
                    check_interrupt=lambda: self.interrupted,
                )
            except Exception as e:
                # Parse failure - show error dialog (Edge case 11)
                result = await self.app.push_screen_wait(
                    ErrorDialog(
                        title="Parse Error",
                        message=f"Failed to parse book:\n{e}",
                        options=[("r", "Retry"), ("q", "Quit")],
                    )
                )
                if result == "r":
                    # Retry - call recursively
                    await self._run_pipeline()
                    return
                else:
                    self.aborted = True
                    self._show_aborted("Parse failed.")
                    return

            if self.interrupted:
                raise InterruptedError()

            if extracted_count > 0:
                self.query_one("#step-1", Static).update(
                    f"[bold cyan][1/3][/] Parsing...\n"
                    f"  [green]\u2713[/] Extracted {extracted_count} sections to {chapters_dir}/"
                )
            else:
                self.query_one("#step-1", Static).update(
                    f"[bold cyan][1/3][/] Parsing...\n"
                    f"  [green]\u2713[/] Using existing sections in {chapters_dir}/"
                )

            # Step 2: Generate
            self.query_one("#step-2", Static).update(
                "[bold cyan][2/3][/] Generating flashcards..."
            )

            # Calculate what needs to be generated
            gen_status = get_generation_status(chapters_dir, config.selected_indices)
            self.to_generate = [
                idx
                for idx in config.selected_indices
                if config.force_regenerate or not gen_status.get(idx, False)
            ]
            self.previously_generated = [
                idx
                for idx in config.selected_indices
                if not config.force_regenerate and gen_status.get(idx, False)
            ]

            if self.to_generate:
                # Show progress bar
                progress_bar = self.query_one("#generation-progress", ProgressBar)
                progress_bar.display = True
                progress_bar.total = len(self.to_generate)
                progress_bar.progress = 0

                current_section = self.query_one("#current-section", Static)
                current_section.display = True

                # Build section tree for deck name calculation
                section_tree = build_section_tree(parsed, chapters_dir)

                # Generate sections one by one with error handling
                self.newly_generated_count = await self._generate_with_error_handling(
                    parsed,
                    config,
                    chapters_dir,
                    section_tree,
                    progress_bar,
                    current_section,
                )

                if self.aborted:
                    return

                if self.interrupted:
                    raise InterruptedError()

                progress_bar.progress = len(self.to_generate)
                current_section.display = False

                status_msg = f"Generated cards for {self.newly_generated_count} sections"
                if self.skipped_sections:
                    status_msg += f" (skipped {len(self.skipped_sections)})"

                self.query_one("#step-2", Static).update(
                    f"[bold cyan][2/3][/] Generating flashcards...\n"
                    f"  [green]\u2713[/] {status_msg}"
                )
            else:
                self.query_one("#step-2", Static).update(
                    f"[bold cyan][2/3][/] Generating flashcards...\n"
                    f"  [green]\u2713[/] All sections already generated"
                )

            # Step 3: Export
            self.query_one("#step-3", Static).update("[bold cyan][3/3][/] Exporting...")

            output_file = config.output_dir / "all_cards.txt"
            total_cards, basic_count, cloze_count = await run_export_step(
                parsed,
                config,
                chapters_dir,
                output_file,
            )

            if total_cards > 0:
                self.query_one("#step-3", Static).update(
                    f"[bold cyan][3/3][/] Exporting...\n"
                    f"  [green]\u2713[/] Exported {total_cards} cards to {output_file}"
                )

                # Show completion panel
                self._show_completion(total_cards, basic_count, cloze_count, output_file)
            else:
                self.query_one("#step-3", Static).update(
                    f"[bold cyan][3/3][/] Exporting...\n"
                    f"  [yellow]No cards to export[/]"
                )

            self.completed = True
            self._update_help_text()

        except InterruptedError:
            self._show_interrupted()

    async def _generate_with_error_handling(
        self,
        parsed,
        config,
        chapters_dir,
        section_tree,
        progress_bar,
        current_section,
    ) -> int:
        """Generate sections with error handling for API errors.

        Returns the count of successfully generated sections.
        """
        from collections import defaultdict

        from rich.console import Console

        from anki_gen.commands.generate import execute_generate
        from anki_gen.tui.state import calculate_deck_name_for_chapter
        from anki_gen.tui.widgets.error_dialog import ErrorDialog

        generated_count = 0

        if config.deck_name is None:
            # Auto mode: use depth-based deck names
            deck_groups: dict[str, list[int]] = defaultdict(list)

            for idx in self.to_generate:
                deck_name = calculate_deck_name_for_chapter(
                    idx, section_tree, config.depth_level, parsed.metadata.title
                )
                deck_groups[deck_name].append(idx)

            total_groups = len(deck_groups)
            quiet_console = Console(quiet=True)

            for i, (deck_name, chapter_indices) in enumerate(deck_groups.items()):
                if self.interrupted or self.aborted:
                    break

                progress_bar.progress = i
                current_section.update(f"  Current: {deck_name}")

                success = await self._generate_single_group(
                    chapters_dir,
                    config,
                    quiet_console,
                    chapter_indices,
                    deck_name,
                )

                if success:
                    generated_count += len(chapter_indices)
                elif self.aborted:
                    break
        else:
            # Custom deck name - generate all at once
            progress_bar.progress = 0
            current_section.update(f"  Current: {config.deck_name}")

            quiet_console = Console(quiet=True)
            success = await self._generate_single_group(
                chapters_dir,
                config,
                quiet_console,
                self.to_generate,
                config.deck_name,
            )

            if success:
                generated_count = len(self.to_generate)

        return generated_count

    async def _generate_single_group(
        self,
        chapters_dir,
        config,
        quiet_console,
        chapter_indices: list[int],
        deck_name: str,
    ) -> bool:
        """Generate a single group of chapters.

        Returns True if successful, False if skipped or aborted.
        """
        from anki_gen.commands.generate import execute_generate
        from anki_gen.tui.widgets.error_dialog import ErrorDialog

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                execute_generate(
                    chapters_dir=chapters_dir,
                    max_cards=config.max_cards,
                    model=config.model,
                    dry_run=False,
                    quiet=True,
                    console=quiet_console,
                    chapters=",".join(str(idx + 1) for idx in chapter_indices),
                    deck=deck_name,
                    tags=config.tags or None,
                    force=config.force_regenerate,
                )
                return True

            except Exception as e:
                retry_count += 1

                # Edge case 4: API errors during generation
                result = await self.app.push_screen_wait(
                    ErrorDialog(
                        title="Generation Error",
                        message=f"Failed to generate cards for '{deck_name}':\n{e}",
                        options=[("r", "Retry"), ("s", "Skip"), ("a", "Abort")],
                    )
                )

                if result == "r":
                    # Retry
                    continue
                elif result == "s":
                    # Skip this section
                    self.skipped_sections.extend(chapter_indices)
                    return False
                else:
                    # Abort
                    self.aborted = True
                    self._show_aborted(f"Generation aborted at '{deck_name}'.")
                    return False

        # Max retries exceeded
        self.skipped_sections.extend(chapter_indices)
        self.notify(f"Skipped '{deck_name}' after {max_retries} failed attempts.", severity="warning")
        return False

    def _show_aborted(self, reason: str) -> None:
        """Show the aborted message."""
        completion_panel = self.query_one("#completion-panel", Static)
        completion_panel.update(
            f"[red][bold]Operation aborted.[/bold]\n\n"
            f"{reason}\n\n"
            f"Completed sections are saved. You can resume by running the command again.[/]"
        )
        completion_panel.display = True
        self.completed = True
        self._update_help_text()

    def _show_completion(
        self, total_cards: int, basic_count: int, cloze_count: int, output_file
    ) -> None:
        """Show the completion panel."""
        newly_gen_sections = self.newly_generated_count
        prev_gen_sections = len(self.previously_generated)

        summary_lines = [
            "[bold]Complete[/]",
            "",
            f"  Total cards in export: {total_cards} ({basic_count} basic, {cloze_count} cloze)",
        ]

        if newly_gen_sections > 0 or prev_gen_sections > 0:
            summary_lines.append(
                f"    \u2022 Newly generated: {newly_gen_sections} sections"
            )
            summary_lines.append(
                f"    \u2022 Previously generated: {prev_gen_sections} sections"
            )

        summary_lines.extend([
            "",
            f"  Import file: {output_file}",
            "",
            "  [dim]Next: Import into Anki via File \u2192 Import[/]",
        ])

        completion_panel = self.query_one("#completion-panel", Static)
        completion_panel.update("\n".join(summary_lines))
        completion_panel.display = True

    def _show_interrupted(self) -> None:
        """Show the interrupted message."""
        completion_panel = self.query_one("#completion-panel", Static)
        completion_panel.update(
            "[yellow][bold]Operation interrupted.[/bold]\n\n"
            "Completed sections are saved. You can resume by running the command again.[/]"
        )
        completion_panel.display = True
        self.completed = True
        self._update_help_text()

    def _update_help_text(self) -> None:
        """Update the help text."""
        if self.completed:
            help_text = "[Enter] Done  [Q] Quit"
        else:
            help_text = "[Ctrl+C] Cancel"
        self.query_one("#help-text", Static).update(f"[dim]{help_text}[/]")

    def action_interrupt(self) -> None:
        """Handle interrupt request."""
        if not self.completed:
            self.interrupted = True
            self.notify("Interrupt received. Finishing current operation...", severity="warning")

    def action_finish(self) -> None:
        """Finish and exit."""
        if self.completed:
            self.app.exit(0)

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit(0)
