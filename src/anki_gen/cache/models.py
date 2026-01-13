"""Cache data models."""

from datetime import datetime

from pydantic import BaseModel, Field

from anki_gen.models.book import BookMetadata, TOCEntry
from anki_gen.models.extraction import ExtractionMethod


class CacheMetadata(BaseModel):
    """Metadata for cache invalidation."""

    file_path: str  # Path to source file (EPUB, PDF, etc.)
    file_hash: str
    file_size: int
    file_mtime: float
    cached_at: datetime = Field(default_factory=datetime.now)
    cache_version: str = "1.1"  # Bumped for format change


class CachedChapter(BaseModel):
    """Cached chapter info (without raw content)."""

    id: str
    title: str
    index: int
    file_name: str
    word_count: int
    has_images: bool = False
    # PDF-specific fields
    page_start: int | None = None
    page_end: int | None = None
    extraction_confidence: float = 1.0
    extraction_method: ExtractionMethod = ExtractionMethod.EPUB_NATIVE
    level: int = 0


class CachedBookStructure(BaseModel):
    """Complete cached structure of a book file (EPUB, PDF, etc.)."""

    cache_metadata: CacheMetadata
    book_metadata: BookMetadata
    toc: list[TOCEntry] = Field(default_factory=list)
    chapters: list[CachedChapter]
    spine_order: list[str] = Field(default_factory=list)
    # Format-specific fields
    source_format: str = "epub"  # "epub" | "pdf"
    extraction_method: ExtractionMethod = ExtractionMethod.EPUB_NATIVE
    extraction_confidence: float = 1.0


# Backward compatibility alias
CachedEpubStructure = CachedBookStructure


class CacheIndex(BaseModel):
    """Index mapping file paths to cache entries."""

    entries: dict[str, str] = Field(default_factory=dict)  # path -> hash
