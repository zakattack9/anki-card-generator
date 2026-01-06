"""Data models for EPUB structure."""

from pydantic import BaseModel, Field


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


class BookMetadata(BaseModel):
    """Book-level metadata."""

    title: str
    authors: list[str] = Field(default_factory=list)
    language: str | None = None
    publisher: str | None = None
    publication_date: str | None = None


class ParsedEpub(BaseModel):
    """Complete parsed EPUB structure."""

    metadata: BookMetadata
    toc: list[TOCEntry]
    chapters: list[Chapter]
    spine_order: list[str] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True
