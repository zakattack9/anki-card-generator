"""Data models for output format."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChapterMetadata(BaseModel):
    """Metadata accompanying chapter content."""

    chapter_id: str
    chapter_index: int
    title: str
    source_file: str
    source_path: str  # Generic path (works for both EPUB and PDF)
    extracted_at: datetime = Field(default_factory=datetime.now)
    word_count: int
    character_count: int
    paragraph_count: int
    # New fields for PDF support
    page_start: int | None = None
    page_end: int | None = None
    extraction_confidence: float = 1.0
    extraction_method: str = "epub_native"

    # Backward compatibility property
    @property
    def source_epub(self) -> str:
        """Deprecated: Use source_path instead."""
        return self.source_path


class ChapterOutput(BaseModel):
    """Complete chapter output for AI consumption."""

    metadata: ChapterMetadata
    content: str
    format: Literal["markdown", "text", "html"] = "markdown"
    ai_processing: dict | None = None


class BookOutput(BaseModel):
    """Complete book output manifest."""

    book_title: str
    authors: list[str]
    total_chapters: int
    extracted_chapters: list[int]
    output_directory: str
    created_at: datetime = Field(default_factory=datetime.now)
    chapters: list[ChapterMetadata]
    # New fields for multi-format support
    source_format: str = "epub"
    extraction_method: str = "epub_native"
    extraction_confidence: float = 1.0
    warnings: list[str] = Field(default_factory=list)
