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
    source_epub: str
    extracted_at: datetime = Field(default_factory=datetime.now)
    word_count: int
    character_count: int
    paragraph_count: int


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
