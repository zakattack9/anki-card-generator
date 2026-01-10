"""Data models for EPUB structure.

This module is maintained for backward compatibility.
New code should import from anki_gen.models.book instead.
"""

# Re-export all models from book.py for backward compatibility
from anki_gen.models.book import (
    BookMetadata,
    Chapter,
    ParsedBook,
    ParsedEpub,
    TOCEntry,
)

__all__ = [
    "TOCEntry",
    "Chapter",
    "BookMetadata",
    "ParsedEpub",
    "ParsedBook",
]
