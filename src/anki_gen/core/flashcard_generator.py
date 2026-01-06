"""Flashcard generation using Gemini CLI."""

import json
import subprocess
import time
from datetime import datetime

from anki_gen.models.flashcard import (
    BasicCard,
    ClozeCard,
    GeminiResponse,
    GenerationMetadata,
    GenerationResult,
)
from anki_gen.models.output import ChapterOutput


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

    DEFAULT_MODEL = "gemini-3-pro"
    TIMEOUT_SECONDS = 300  # 5 minutes

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_cards: int | None = None,
    ):
        self.model = model
        self.max_cards = max_cards

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

    def _call_gemini(self, prompt: str) -> GeminiResponse:
        """Call Gemini CLI and return parsed response."""
        cmd = [
            "gemini",
            "-m",
            self.model,
            prompt,
            "--output-format",
            "json",
        ]

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

        try:
            data = json.loads(result.stdout)
            response = GeminiResponse.model_validate(data)
        except json.JSONDecodeError as e:
            raise GeminiError("PARSE_ERROR", f"Failed to parse JSON response: {e}")

        if response.error:
            raise GeminiError(
                response.error.get("type", "UNKNOWN"),
                response.error.get("message", "Unknown error"),
                response.error.get("code"),
            )

        return response

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
        response = self._call_gemini(prompt)
        return self._parse_basic_cards(response.response)

    def generate_cloze(self, chapter: ChapterOutput) -> list[ClozeCard]:
        """Generate cloze flashcards for a chapter."""
        prompt = self._build_cloze_prompt(chapter)
        response = self._call_gemini(prompt)
        return self._parse_cloze_cards(response.response)

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
