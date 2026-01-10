"""Data models."""

from anki_gen.models.book import (
    BookMetadata,
    Chapter,
    ParsedBook,
    ParsedEpub,
    TOCEntry,
)
from anki_gen.models.extraction import (
    DetectionResult,
    ExtractionMethod,
    Section,
)
from anki_gen.models.output import (
    BookOutput,
    ChapterMetadata,
    ChapterOutput,
)

__all__ = [
    # Book models
    "TOCEntry",
    "Chapter",
    "BookMetadata",
    "ParsedBook",
    "ParsedEpub",
    # Extraction models
    "ExtractionMethod",
    "Section",
    "DetectionResult",
    # Output models
    "ChapterMetadata",
    "ChapterOutput",
    "BookOutput",
]
