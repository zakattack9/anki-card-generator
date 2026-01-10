"""Data models for book structure (EPUB and PDF)."""

from pydantic import BaseModel, Field

from anki_gen.models.extraction import ExtractionMethod


class TOCEntry(BaseModel):
    """Single entry in table of contents."""

    id: str
    title: str
    href: str
    level: int = 0
    children: list["TOCEntry"] = Field(default_factory=list)


class Chapter(BaseModel):
    """Chapter content and metadata."""

    id: str
    title: str
    index: int
    file_name: str
    raw_content: bytes = b""
    word_count: int = 0
    has_images: bool = False
    # New fields for PDF support
    page_start: int | None = None
    page_end: int | None = None
    extraction_confidence: float = 1.0
    extraction_method: ExtractionMethod = ExtractionMethod.EPUB_NATIVE


class BookMetadata(BaseModel):
    """Book-level metadata."""

    title: str
    authors: list[str] = Field(default_factory=list)
    language: str | None = None
    publisher: str | None = None
    publication_date: str | None = None


class ParsedBook(BaseModel):
    """Complete parsed book structure (unified for EPUB/PDF)."""

    metadata: BookMetadata
    toc: list[TOCEntry] = Field(default_factory=list)
    chapters: list[Chapter]
    spine_order: list[str] = Field(default_factory=list)
    source_format: str = "epub"  # "epub" | "pdf"
    extraction_method: ExtractionMethod = ExtractionMethod.EPUB_NATIVE
    extraction_confidence: float = 1.0
    warnings: list[str] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True


# Backward compatibility alias
ParsedEpub = ParsedBook
