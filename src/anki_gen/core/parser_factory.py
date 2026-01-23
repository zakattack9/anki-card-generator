"""Factory for creating book parsers based on file format."""

from abc import ABC, abstractmethod
from pathlib import Path

from anki_gen.models.book import BookMetadata, ParsedBook


class BookParser(ABC):
    """Abstract base class for book parsers."""

    @abstractmethod
    def parse(self) -> ParsedBook:
        """Parse the book and return complete structure."""
        pass

    @abstractmethod
    def get_metadata(self) -> BookMetadata:
        """Extract book metadata."""
        pass


class ParserFactory:
    """Factory for creating appropriate parser based on file format."""

    SUPPORTED_FORMATS = {
        ".epub": "epub",
        ".pdf": "pdf",
    }

    @classmethod
    def create(cls, path: Path, pages_per_chunk: int | None = None) -> BookParser:
        """Create appropriate parser for the given file.

        Args:
            path: Path to the book file (EPUB or PDF)
            pages_per_chunk: If set, skip section detection and use
                page-based chunking with this many pages per section (PDF only)

        Returns:
            BookParser instance for the file type

        Raises:
            ValueError: If file format is not supported
            FileNotFoundError: If file does not exist
        """
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        suffix = path.suffix.lower()

        if suffix not in cls.SUPPORTED_FORMATS:
            supported = ", ".join(cls.SUPPORTED_FORMATS.keys())
            raise ValueError(
                f"Unsupported format: {suffix}. Supported formats: {supported}"
            )

        if suffix == ".epub":
            from anki_gen.core.epub_parser import EpubParser

            return EpubParser(path)
        elif suffix == ".pdf":
            from anki_gen.core.pdf_parser import PdfParser

            return PdfParser(path, pages_per_chunk=pages_per_chunk)

        # Should never reach here, but satisfy type checker
        raise ValueError(f"Unsupported format: {suffix}")

    @classmethod
    def detect_format(cls, path: Path) -> str:
        """Detect file format from extension.

        Args:
            path: Path to the book file

        Returns:
            Format string ("epub", "pdf", or "unknown")
        """
        suffix = path.suffix.lower()
        return cls.SUPPORTED_FORMATS.get(suffix, "unknown")

    @classmethod
    def is_supported(cls, path: Path) -> bool:
        """Check if file format is supported.

        Args:
            path: Path to the book file

        Returns:
            True if format is supported
        """
        return path.suffix.lower() in cls.SUPPORTED_FORMATS
