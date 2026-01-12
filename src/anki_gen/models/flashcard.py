"""Flashcard data models."""

import re
from datetime import datetime

from pydantic import BaseModel, Field


class BasicCard(BaseModel):
    """Basic Q&A flashcard."""

    front: str  # Question
    back: str  # Answer
    tags: list[str] = Field(default_factory=list)
    guid: str = ""


class ClozeCard(BaseModel):
    """Cloze deletion flashcard."""

    text: str  # Contains {{c1::...}} markers
    back_extra: str = ""  # Additional info shown on back
    tags: list[str] = Field(default_factory=list)
    guid: str = ""


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


class AnkiExportConfig(BaseModel):
    """Configuration for Anki export."""

    deck_name: str
    global_tags: list[str] = Field(default_factory=list)
    book_slug: str
    chapter_id: str

    @staticmethod
    def sanitize_deck_name(name: str) -> str:
        """Sanitize deck name for Anki compatibility.

        Handles:
        - Control characters (newlines, tabs, vertical tabs, etc.)
        - Anki's :: hierarchy separator
        - File system unsafe characters
        - Anki field separator (|)
        """
        # Replace control characters with space
        sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", name)
        # Replace :: (Anki hierarchy separator) with dash
        sanitized = re.sub(r"::", "-", sanitized)
        # Replace separator-like characters with space (to avoid run-on words)
        sanitized = re.sub(r"[/|]", " ", sanitized)
        # Remove other problematic characters (file system / Anki unsafe)
        sanitized = re.sub(r'[<>:"\\?*]', "", sanitized)
        # Collapse multiple spaces
        sanitized = re.sub(r" +", " ", sanitized)
        return sanitized.strip()

    @staticmethod
    def slugify(text: str) -> str:
        """Convert text to lowercase slug with hyphens."""
        # Lowercase
        slug = text.lower()
        # Replace spaces and underscores with hyphens
        slug = re.sub(r"[\s_]+", "-", slug)
        # Remove non-alphanumeric except hyphens
        slug = re.sub(r"[^a-z0-9-]", "", slug)
        # Remove multiple consecutive hyphens
        slug = re.sub(r"-+", "-", slug)
        return slug.strip("-")

    @staticmethod
    def sanitize_tag(tag: str) -> str:
        """Sanitize a single tag for Anki compatibility."""
        # Lowercase
        sanitized = tag.lower()
        # Replace spaces with hyphens
        sanitized = re.sub(r"\s+", "-", sanitized)
        # Remove non-alphanumeric except hyphens
        sanitized = re.sub(r"[^a-z0-9-]", "", sanitized)
        # Remove multiple consecutive hyphens
        sanitized = re.sub(r"-+", "-", sanitized)
        return sanitized.strip("-")

    @staticmethod
    def escape_field(field: str, separator: str = "|") -> str:
        """Escape a field for Anki's CSV import format.

        Per Anki docs: if a field contains the separator or quotes,
        wrap in quotes and double any internal quotes.
        """
        if separator in field or '"' in field:
            # Escape quotes by doubling them
            escaped = field.replace('"', '""')
            return f'"{escaped}"'
        return field


class GenerationResult(BaseModel):
    """Result of flashcard generation for a chapter."""

    metadata: GenerationMetadata
    basic_cards: list[BasicCard]
    cloze_cards: list[ClozeCard]

    def to_basic_txt(self) -> str:
        """Export basic cards as pipe-separated text (legacy format)."""
        return "\n".join(f"{c.front}|{c.back}" for c in self.basic_cards)

    def to_cloze_txt(self) -> str:
        """Export cloze cards as pipe-separated text (legacy format)."""
        return "\n".join(f"{c.text}|{c.back_extra}" for c in self.cloze_cards)

    def to_combined_txt(self, config: AnkiExportConfig) -> str:
        """Export all cards as single Anki-importable file with headers."""
        # Build file headers
        lines = [
            "#separator:Pipe",
            "#html:true",
            f"#deck:{config.deck_name}",
            f"#tags:anki-gen {config.book_slug}",
            "#notetype column:1",
            "#tags column:4",
            "#guid column:5",
            "#columns:Note Type|Field 1|Field 2|Tags|GUID",
        ]

        # Add global tags if specified
        if config.global_tags:
            sanitized_global = " ".join(
                AnkiExportConfig.sanitize_tag(t) for t in config.global_tags
            )
            lines[3] = f"#tags:anki-gen {config.book_slug} {sanitized_global}"

        # Add all cards (basic first, then cloze)
        for card in self.basic_cards:
            tags_str = " ".join(
                AnkiExportConfig.sanitize_tag(t) for t in card.tags
            )
            # Escape fields containing pipes or quotes (per Anki docs)
            front = AnkiExportConfig.escape_field(card.front)
            back = AnkiExportConfig.escape_field(card.back)
            lines.append(f"Basic|{front}|{back}|{tags_str}|{card.guid}")

        for card in self.cloze_cards:
            tags_str = " ".join(
                AnkiExportConfig.sanitize_tag(t) for t in card.tags
            )
            # Escape fields containing pipes or quotes (per Anki docs)
            text = AnkiExportConfig.escape_field(card.text)
            back_extra = AnkiExportConfig.escape_field(card.back_extra)
            lines.append(f"Cloze|{text}|{back_extra}|{tags_str}|{card.guid}")

        return "\n".join(lines)
