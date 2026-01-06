"""Flashcard generation using Gemini CLI."""

import re
import subprocess
import time
from collections import deque
from datetime import datetime
from typing import TYPE_CHECKING

from anki_gen.models.flashcard import (
    AnkiExportConfig,
    BasicCard,
    ClozeCard,
    GenerationMetadata,
    GenerationResult,
)
from anki_gen.models.output import ChapterOutput

if TYPE_CHECKING:
    from rich.console import Console


class GeminiError(Exception):
    """Error from Gemini CLI."""

    def __init__(self, error_type: str, message: str, code: int | None = None):
        self.error_type = error_type
        self.message = message
        self.code = code
        super().__init__(f"{error_type}: {message}")


UNIFIED_CARD_PROMPT = """You are a world-class Anki flashcard creator. Generate high-quality flashcards from the chapter below.

## Card Type Selection

For EACH fact, choose the optimal card type:

**CLOZE** - Use for:
- Numbers, dates, percentages (e.g., "The House has {{{{c1::435}}}} members")
- Names of people, places, documents (e.g., "{{{{c1::Thomas Jefferson}}}} wrote...")
- Terminology and clause names (e.g., "The {{{{c1::Supremacy}}}} Clause...")
- Simple factual associations where fill-in-blank reads naturally

**BASIC** - Use for:
- "Why" or "How" questions requiring explanation
- Answers with multiple parts or lists
- Definitions needing full context
- Comparisons or contrasts
- Processes or procedures

## Rules

1. Each fact appears ONCE - no duplicates between card types
2. Maximum 2 cloze deletions per card ({{{{c1::...}}}} and {{{{c2::...}}}} only)
3. One atomic fact per card
4. Cards must be self-contained (no assumed prior knowledge)
5. Use your knowledge to add context that makes cards complete

{max_cards_instruction}

## Output Format

Each card on a new line with pipe separator:
- Basic: `Basic|Question|Answer|tags`
- Cloze: `Cloze|Cloze text with {{{{c1::deletions}}}}|Back extra info|tags`

Tags: 1-3 lowercase topic words, space-separated (e.g., "constitution amendment-process")

Formatting:
- Math: \\( inline \\) or \\[ block \\]
- Chemistry: \\( \\ce{{H2O}} \\)
- Lists within fields: use <br> (no actual newlines)
- Bold: <b>text</b>, Italic: <i>text</i>

Return ONLY the cards, no other text.

## Chapter Title: {chapter_title}

## Chapter Content:
{chapter_content}"""


class FlashcardGenerator:
    """Generate flashcards from chapter content using Gemini."""

    DEFAULT_MODEL = "gemini-3-pro-preview"
    TIMEOUT_SECONDS = 300  # 5 minutes
    STREAM_LINES = 10  # Number of lines to show in streaming output

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_cards: int | None = None,
        console: "Console | None" = None,
        stream: bool = True,
    ):
        self.model = model
        self.max_cards = max_cards
        self.console = console
        self.stream = stream and console is not None

    def _get_max_cards_instruction(self) -> str:
        """Get instruction for max cards."""
        if self.max_cards:
            return f"Generate at most {self.max_cards} cards total (combining both Basic and Cloze)."
        return "Be comprehensive. Cover all key concepts, but avoid redundancy."

    def _build_prompt(self, chapter: ChapterOutput) -> str:
        """Build the unified prompt for card generation."""
        return UNIFIED_CARD_PROMPT.format(
            max_cards_instruction=self._get_max_cards_instruction(),
            chapter_title=chapter.metadata.title,
            chapter_content=chapter.content,
        )

    def _call_gemini_streaming(self, prompt: str) -> str:
        """Call Gemini CLI with streaming output display.

        Uses a pseudo-terminal (pty) to get unbuffered output from Gemini CLI.
        Returns the full response text.
        """
        import os
        import pty
        import select

        from rich.live import Live
        from rich.panel import Panel
        from rich.text import Text

        cmd = ["gemini", "-m", self.model, prompt]

        lines_buffer: deque[str] = deque(maxlen=self.STREAM_LINES)
        all_output: list[str] = []
        current_line = ""

        def render_panel() -> Panel:
            content = Text()
            for i, line in enumerate(lines_buffer):
                if i > 0:
                    content.append("\n")
                # Truncate long lines for display
                display_line = line[:100] + "..." if len(line) > 100 else line
                content.append(display_line, style="dim")
            return Panel(
                content,
                title="[cyan]Generating flashcards[/]",
                subtitle=f"[dim]{len(all_output)} cards[/]",
                border_style="blue",
            )

        # Create a pseudo-terminal to get unbuffered output
        master_fd, slave_fd = pty.openpty()

        try:
            process = subprocess.Popen(
                cmd,
                stdout=slave_fd,
                stderr=slave_fd,
                stdin=slave_fd,
                close_fds=True,
            )
            os.close(slave_fd)  # Close slave in parent process

            with Live(
                render_panel(), console=self.console, refresh_per_second=4
            ) as live:
                start_time = time.time()

                while True:
                    # Check timeout
                    if time.time() - start_time > self.TIMEOUT_SECONDS:
                        process.kill()
                        raise GeminiError(
                            "TIMEOUT", f"Request timed out after {self.TIMEOUT_SECONDS}s"
                        )

                    # Check if there's data to read
                    ready, _, _ = select.select([master_fd], [], [], 0.1)

                    if ready:
                        try:
                            data = os.read(master_fd, 1024).decode("utf-8", errors="replace")
                            if not data:
                                break

                            # Process the data character by character for line detection
                            for char in data:
                                if char == "\n":
                                    if current_line.strip():
                                        lines_buffer.append(current_line)
                                        all_output.append(current_line)
                                        live.update(render_panel())
                                    current_line = ""
                                elif char != "\r":
                                    current_line += char

                        except OSError:
                            break

                    # Check if process has finished
                    if process.poll() is not None:
                        # Read any remaining data
                        try:
                            while True:
                                ready, _, _ = select.select([master_fd], [], [], 0.1)
                                if not ready:
                                    break
                                data = os.read(master_fd, 1024).decode("utf-8", errors="replace")
                                if not data:
                                    break
                                for char in data:
                                    if char == "\n":
                                        if current_line.strip():
                                            lines_buffer.append(current_line)
                                            all_output.append(current_line)
                                        current_line = ""
                                    elif char != "\r":
                                        current_line += char
                        except OSError:
                            pass
                        break

                # Don't forget any trailing content
                if current_line.strip():
                    lines_buffer.append(current_line)
                    all_output.append(current_line)
                    live.update(render_panel())

            # Wait for process to fully terminate and get return code
            process.wait()

        finally:
            os.close(master_fd)

        # Only raise error for actual non-zero exit codes
        if process.returncode and process.returncode != 0:
            raise GeminiError("CLI_ERROR", f"Gemini exited with code {process.returncode}")

        return "\n".join(all_output)

    def _call_gemini_batch(self, prompt: str) -> str:
        """Call Gemini CLI without streaming (quiet mode).

        Returns the full response text.
        """
        cmd = ["gemini", "-m", self.model, prompt]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            raise GeminiError(
                "TIMEOUT", f"Request timed out after {self.TIMEOUT_SECONDS}s"
            )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            raise GeminiError("CLI_ERROR", error_msg)

        return result.stdout

    def _call_gemini(self, prompt: str) -> str:
        """Call Gemini CLI and return response text."""
        if self.stream:
            return self._call_gemini_streaming(prompt)
        return self._call_gemini_batch(prompt)

    def _extract_chapter_id(self, source_file: str) -> str:
        """Extract chapter ID from source filename.

        Examples:
            chapter_011.json -> ch011
            chapter_001.json -> ch001
        """
        match = re.search(r"chapter_(\d+)", source_file)
        if match:
            return f"ch{match.group(1)}"
        return "ch000"

    def _parse_unified_output(
        self, response_text: str, chapter_id: str
    ) -> tuple[list[BasicCard], list[ClozeCard], list[str]]:
        """Parse unified output into basic and cloze cards.

        Returns: (basic_cards, cloze_cards, warnings)
        """
        basic_cards: list[BasicCard] = []
        cloze_cards: list[ClozeCard] = []
        warnings: list[str] = []
        card_sequence = 0

        lines = response_text.strip().split("\n")

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or "|" not in line:
                continue

            # Split into parts
            parts = line.split("|")
            if len(parts) < 3:
                warnings.append(f"Line {line_num}: Malformed card (fewer than 3 fields)")
                continue

            card_type = parts[0].strip()
            field1 = parts[1].strip()
            field2 = parts[2].strip()

            # Extract tags (4th field if present)
            tags: list[str] = []
            if len(parts) >= 4:
                raw_tags = parts[3].strip()
                if raw_tags:
                    # Split on spaces, filter empty
                    tags = [
                        AnkiExportConfig.sanitize_tag(t)
                        for t in raw_tags.split()
                        if t.strip()
                    ]

            # Generate GUID
            card_sequence += 1
            guid = f"{chapter_id}-{card_sequence:03d}"

            if card_type == "Basic":
                if not field1 or not field2:
                    warnings.append(f"Line {line_num}: Empty question or answer")
                    continue
                basic_cards.append(BasicCard(
                    front=field1,
                    back=field2,
                    tags=tags,
                    guid=guid,
                ))
            elif card_type == "Cloze":
                if not field1:
                    warnings.append(f"Line {line_num}: Empty cloze text")
                    continue
                # Validate cloze markers
                if "{{c" not in field1:
                    warnings.append(f"Line {line_num}: Cloze card missing {{{{c1::...}}}} markers")
                    continue
                cloze_cards.append(ClozeCard(
                    text=field1,
                    back_extra=field2,
                    tags=tags,
                    guid=guid,
                ))
            else:
                warnings.append(f"Line {line_num}: Unknown card type '{card_type}'")

        return basic_cards, cloze_cards, warnings

    def generate(self, chapter: ChapterOutput, source_file: str) -> GenerationResult:
        """Generate flashcards for a chapter using unified prompt."""
        start_time = time.time()

        # Build and send prompt
        prompt = self._build_prompt(chapter)
        response_text = self._call_gemini(prompt)

        # Extract chapter ID for GUIDs
        chapter_id = self._extract_chapter_id(source_file)

        # Parse unified output
        basic_cards, cloze_cards, warnings = self._parse_unified_output(
            response_text, chapter_id
        )

        # Log warnings if console available
        if warnings and self.console:
            for warning in warnings:
                self.console.print(f"  [yellow]Warning:[/] {warning}")

        # Warn if no cards generated
        if not basic_cards and not cloze_cards:
            if self.console:
                self.console.print("  [yellow]Warning:[/] No valid cards generated")

        generation_time = time.time() - start_time

        metadata = GenerationMetadata(
            chapter_id=chapter.metadata.chapter_id,
            chapter_title=chapter.metadata.title,
            source_file=source_file,
            generated_at=datetime.now(),
            model_used=self.model,
            basic_count=len(basic_cards),
            cloze_count=len(cloze_cards),
            total_count=len(basic_cards) + len(cloze_cards),
            generation_time_seconds=generation_time,
        )

        return GenerationResult(
            metadata=metadata,
            basic_cards=basic_cards,
            cloze_cards=cloze_cards,
        )
