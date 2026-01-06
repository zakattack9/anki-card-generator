"""Flashcard data models."""

from datetime import datetime

from pydantic import BaseModel, Field


class BasicCard(BaseModel):
    """Basic Q&A flashcard."""

    front: str  # Question
    back: str  # Answer


class ClozeCard(BaseModel):
    """Cloze deletion flashcard."""

    text: str  # Contains {{c1::...}} markers
    back_extra: str = ""  # Additional info shown on back


class GenerationMetadata(BaseModel):
    """Metadata about the flashcard generation process."""

    chapter_id: str
    chapter_title: str
    source_file: str
    generated_at: datetime = Field(default_factory=datetime.now)
    model_used: str
    basic_count: int
    cloze_count: int
    total_count: int
    generation_time_seconds: float


class GenerationResult(BaseModel):
    """Result of flashcard generation for a chapter."""

    metadata: GenerationMetadata
    basic_cards: list[BasicCard]
    cloze_cards: list[ClozeCard]

    def to_basic_txt(self) -> str:
        """Export basic cards as pipe-separated text."""
        return "\n".join(f"{c.front}|{c.back}" for c in self.basic_cards)

    def to_cloze_txt(self) -> str:
        """Export cloze cards as pipe-separated text."""
        return "\n".join(f"{c.text}|{c.back_extra}" for c in self.cloze_cards)


class GeminiResponse(BaseModel):
    """Response structure from Gemini CLI."""

    response: str
    stats: dict | None = None
    error: dict | None = None
