"""Flashcard generation using Gemini CLI."""

import subprocess
import time
from collections import deque
from datetime import datetime
from typing import TYPE_CHECKING

from anki_gen.models.flashcard import (
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


BASIC_CARD_PROMPT = """You are a world-class Anki flashcard creator that helps students remember facts, concepts, and ideas.

You will be given a chapter from a book.

1. Identify key high-level concepts and ideas presented, including relevant equations. If the content is math or physics-heavy, focus on concepts. If it isn't heavy on concepts, focus on facts.
2. Use your own knowledge to flesh out additional details (facts, dates, equations) to ensure flashcards are self-contained.
3. Make question-answer cards based on the content.
4. Keep questions and answers roughly in the same order as they appear in the chapter.

{max_cards_instruction}

**Output Format:**
- Each flashcard on a new line
- Use pipe separator | between question and answer
- Math: wrap with \\( ... \\) for inline, \\[ ... \\] for block
- Chemistry: use \\( \\ce{{H2O}} \\) format for MathJax
- No newlines within a card - use <br> for lists
- Bold: <b>text</b>, Italic: <i>text</i>
- No header row
- Return ONLY the cards, no other text

**Chapter Title:** {chapter_title}

**Chapter Content:**
{chapter_content}"""

CLOZE_CARD_PROMPT = """You are a world-class Anki cloze-deletion flashcard creator.

You will be given a chapter from a book.

1. Identify key concepts, facts, dates, definitions, and equations for long-term recall.
2. Expand briefly on each point with extra context so cards are self-contained.
3. Convert each point into well-formed cloze deletions:
   - Use {{{{c1::hidden text}}}} syntax
   - Use c2, c3 only if a second deletion is really necessary
   - Keep one atomic fact per cloze
   - Add hints if helpful: {{{{c1::answer::hint}}}}
4. Maintain original order of appearance from the source.

{max_cards_instruction}

**Output Format:**
- Each flashcard on a new line
- Use pipe separator | between cloze text and back extra info
- Math: wrap with \\( ... \\) for inline, \\[ ... \\] for block
- Chemistry: use \\( \\ce{{H2O}} \\) format for MathJax
- No newlines within a card - use <br> for lists
- No header row
- Return ONLY the cards, no other text

**Chapter Title:** {chapter_title}

**Chapter Content:**
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
            return f"Generate at most {self.max_cards} cards total."
        return "Be exhaustive. Cover as much as you can - aim for comprehensive coverage of key concepts."

    def _build_basic_prompt(self, chapter: ChapterOutput) -> str:
        """Build prompt for basic card generation."""
        return BASIC_CARD_PROMPT.format(
            max_cards_instruction=self._get_max_cards_instruction(),
            chapter_title=chapter.metadata.title,
            chapter_content=chapter.content,
        )

    def _build_cloze_prompt(self, chapter: ChapterOutput) -> str:
        """Build prompt for cloze card generation."""
        return CLOZE_CARD_PROMPT.format(
            max_cards_instruction=self._get_max_cards_instruction(),
            chapter_title=chapter.metadata.title,
            chapter_content=chapter.content,
        )

    def _call_gemini_streaming(self, prompt: str, card_type: str) -> str:
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
                title=f"[cyan]Generating {card_type} cards[/]",
                subtitle=f"[dim]{len(all_output)} lines[/]",
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

    def _call_gemini(self, prompt: str, card_type: str = "basic") -> str:
        """Call Gemini CLI and return response text."""
        if self.stream:
            return self._call_gemini_streaming(prompt, card_type)
        return self._call_gemini_batch(prompt)

    def _parse_basic_cards(self, response_text: str) -> list[BasicCard]:
        """Parse pipe-separated basic card output."""
        cards = []
        lines = response_text.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line or "|" not in line:
                continue

            # Split on first pipe only (in case answer contains pipes)
            parts = line.split("|", 1)
            if len(parts) == 2:
                front, back = parts
                cards.append(BasicCard(front=front.strip(), back=back.strip()))

        return cards

    def _parse_cloze_cards(self, response_text: str) -> list[ClozeCard]:
        """Parse pipe-separated cloze card output."""
        cards = []
        lines = response_text.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Split on first pipe only
            if "|" in line:
                parts = line.split("|", 1)
                text, back_extra = parts[0].strip(), parts[1].strip()
            else:
                text, back_extra = line, ""

            # Only add if it contains cloze markers
            if "{{c" in text:
                cards.append(ClozeCard(text=text, back_extra=back_extra))

        return cards

    def generate_basic(self, chapter: ChapterOutput) -> list[BasicCard]:
        """Generate basic flashcards for a chapter."""
        prompt = self._build_basic_prompt(chapter)
        response_text = self._call_gemini(prompt, card_type="basic")
        return self._parse_basic_cards(response_text)

    def generate_cloze(self, chapter: ChapterOutput) -> list[ClozeCard]:
        """Generate cloze flashcards for a chapter."""
        prompt = self._build_cloze_prompt(chapter)
        response_text = self._call_gemini(prompt, card_type="cloze")
        return self._parse_cloze_cards(response_text)

    def generate(self, chapter: ChapterOutput, source_file: str) -> GenerationResult:
        """Generate both basic and cloze flashcards for a chapter."""
        start_time = time.time()

        # Generate basic cards
        basic_cards = self.generate_basic(chapter)

        # Generate cloze cards
        cloze_cards = self.generate_cloze(chapter)

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
