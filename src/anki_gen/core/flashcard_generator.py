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

## CRITICAL: Source Fidelity

- ONLY create cards from information EXPLICITLY stated in the chapter content below
- NEVER add, infer, or introduce facts not present in the source text
- NEVER use your own knowledge to expand or supplement the content
- If the content is just a title, heading, or lacks substantive information, generate ZERO cards
- Generating 0 cards is completely valid and preferred over fabricating content

## Card Type Selection

For EACH fact explicitly stated in the content, choose the optimal card type:

**CLOZE** - Use for:
- Numbers, dates, percentages, quantities
- Names of people, places, documents, laws
- Terminology and key terms within definitions
- Simple factual associations where fill-in-the-blank reads naturally
- Lists or sequences to be memorized (use multiple deletions: c1, c2, c3...)

**BASIC** - Use for:
- "Why" or "How" questions requiring explanation
- Answers with multiple parts that need full context
- Concepts requiring nuanced understanding
- Comparisons, contrasts, cause-effect relationships
- Processes or procedures with reasoning

## Rules

1. **One fact = one card** - Never duplicate facts between card types
2. **Cloze deletions** - Use as many as needed for the concept:
   - Single deletion for isolated facts (dates, names, terms)
   - Multiple deletions (c1, c2, c3...) for lists, sequences, or related items that form ONE concept
   - NEVER use multiple deletions for UNRELATED facts - split into separate cards instead
3. **Atomic concepts** - Each card tests one cohesive idea
4. **Self-contained** - Cards should be understandable using ONLY info from the source
5. **Source-only** - Every fact in a card must come directly from the chapter content
6. **Be comprehensive** - Include all substantive facts from the source; do not skip content
7. **Fragmentary content** - For bullet points or incomplete sentences, create cards only if meaning is clear; do not complete or expand fragmentary text
8. **Avoid pipes** - Do not use the | character in card content

## Cloze Back-Extra Guidelines

The back-extra field provides additional context FROM THE SOURCE, NOT external knowledge.

- Use other facts from the same source that relate to the cloze deletion
- If no additional context exists in the source, use a brief factual description
- NEVER add information not present in the chapter content

GOOD back-extra (from source):
- "Discussed in the previous section on X"
- "One of the three types listed in the source"
- "Comparison introduced in the chapter"
- "Part of the criteria mentioned above"

BAD back-extra (never use):
- Single-word labels: "Number", "Date", "Definition", "Term"
- External knowledge not in the source
- Elaborations you invented

{max_cards_instruction}

## Output Format

Each card on a new line with pipe separator:
- Basic: `Basic|Question|Answer|tags`
- Cloze: `Cloze|Text with {{{{c1::deletion}}}}|Back-extra context|tags`

Tags: 1-3 lowercase hyphenated topic words (e.g., "constitution separation-of-powers")

## Formatting

- Bold: <b>text</b>, Italic: <i>text</i>
- Lists: use <br> for line breaks (no actual newlines within fields)
- Math: \\( inline \\) or \\[ block \\]
- Chemistry: \\( \\ce{{H2O}} \\)

## Examples

GOOD Basic card (explanation from source):
Basic|Why do tectonic plates move?|Convection currents in the mantle create forces that push and pull the plates|geology plate-tectonics

GOOD Cloze (single deletion - fact from source):
Cloze|The Declaration of Independence was signed in {{{{c1::1776}}}}.|Discussed in the founding documents section|history american-revolution

GOOD Cloze (list from source):
Cloze|The three branches of U.S. government are {{{{c1::legislative}}}}, {{{{c2::executive}}}}, and {{{{c3::judicial}}}}.|Framework described in Article I-III|government constitution

GOOD Cloze (related pair from source):
Cloze|{{{{c1::Mitosis}}}} produces identical cells, while {{{{c2::meiosis}}}} produces genetically diverse gametes.|Comparison from the cell division section|biology cell-division

BAD - multiple deletions for UNRELATED facts:
Cloze|The company was founded in {{{{c1::1995}}}} and employs {{{{c2::50,000}}}} people.|Facts|business

BAD - should be cloze, not basic:
Basic|What year did World War II end?|1945|history

BAD - adds information not in source:
Cloze|{{{{c1::Shakespeare}}}} wrote Hamlet, considered one of the greatest tragedies in English literature.|Written around 1600 during the Elizabethan era|literature
(If "greatest tragedies" and "1600" weren't in the source, this is hallucination)

GOOD - uses only source info:
Cloze|{{{{c1::Shakespeare}}}} wrote Hamlet.|Listed among his major works in the chapter|literature drama

## Avoid These Mistakes

- **ADDING INFORMATION NOT IN THE SOURCE** - This is the #1 mistake. Never fabricate facts.
- Creating cards when the content is just a title slide or heading with no substantive info
- Creating both a basic AND cloze card for the same fact
- Using multiple cloze deletions for unrelated facts in one card
- Category-only back-extra ("Number", "Date", "Term")
- Questions that could be answered with a single word/number (use cloze instead)
- Cards that require reading another card to understand
- Trivial facts that aren't worth memorizing

If the chapter content lacks substantive facts to create cards from, return nothing (0 cards).

Return ONLY the cards, no other text.

## Chapter Title: {chapter_title}

## Chapter Content:
{chapter_content}"""


class FlashcardGenerator:
    """Generate flashcards from chapter content using Gemini."""

    DEFAULT_MODEL = "gemini-3-pro-preview"
    TIMEOUT_SECONDS = 600  # 10 minutes
    STREAM_LINES = 10  # Number of lines to show in streaming output

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_cards: int | None = None,
        console: "Console | None" = None,
        stream: bool = True,
        book_slug: str = "",
    ):
        self.model = model
        self.max_cards = max_cards
        self.console = console
        self.stream = stream and console is not None
        self.book_slug = book_slug

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
                            "TIMEOUT",
                            f"Request timed out after {self.TIMEOUT_SECONDS}s",
                        )

                    # Check if there's data to read
                    ready, _, _ = select.select([master_fd], [], [], 0.1)

                    if ready:
                        try:
                            data = os.read(master_fd, 1024).decode(
                                "utf-8", errors="replace"
                            )
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
                                data = os.read(master_fd, 1024).decode(
                                    "utf-8", errors="replace"
                                )
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
            raise GeminiError(
                "CLI_ERROR", f"Gemini exited with code {process.returncode}"
            )

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
                warnings.append(
                    f"Line {line_num}: Malformed card (fewer than 3 fields)"
                )
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

            # Generate GUID (book_slug-chapter_id-sequence for uniqueness across books)
            card_sequence += 1
            if self.book_slug:
                guid = f"{self.book_slug}-{chapter_id}-{card_sequence:03d}"
            else:
                guid = f"{chapter_id}-{card_sequence:03d}"

            if card_type == "Basic":
                if not field1 or not field2:
                    warnings.append(f"Line {line_num}: Empty question or answer")
                    continue
                basic_cards.append(
                    BasicCard(
                        front=field1,
                        back=field2,
                        tags=tags,
                        guid=guid,
                    )
                )
            elif card_type == "Cloze":
                if not field1:
                    warnings.append(f"Line {line_num}: Empty cloze text")
                    continue
                # Validate cloze markers
                if "{{c" not in field1:
                    warnings.append(
                        f"Line {line_num}: Cloze card missing {{{{c1::...}}}} markers"
                    )
                    continue
                cloze_cards.append(
                    ClozeCard(
                        text=field1,
                        back_extra=field2,
                        tags=tags,
                        guid=guid,
                    )
                )
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
