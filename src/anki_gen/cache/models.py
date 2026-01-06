"""Cache data models."""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from anki_gen.models.epub import BookMetadata, TOCEntry


class CacheMetadata(BaseModel):
    """Metadata for cache invalidation."""

    epub_path: str
    file_hash: str
    file_size: int
    file_mtime: float
    cached_at: datetime = Field(default_factory=datetime.now)
    cache_version: str = "1.0"


class CachedChapter(BaseModel):
    """Cached chapter info (without raw content)."""

    id: str
    title: str
    index: int
    file_name: str
    word_count: int
    has_images: bool = False


class CachedEpubStructure(BaseModel):
    """Complete cached structure of an EPUB file."""

    cache_metadata: CacheMetadata
    book_metadata: BookMetadata
    toc: list[TOCEntry]
    chapters: list[CachedChapter]
    spine_order: list[str] = Field(default_factory=list)


class CacheIndex(BaseModel):
    """Index mapping epub paths to cache entries."""

    entries: dict[str, str] = Field(default_factory=dict)  # path -> hash
