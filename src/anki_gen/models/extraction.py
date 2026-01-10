"""Data models for document structure extraction."""

from enum import Enum

from pydantic import BaseModel, Field


class ExtractionMethod(str, Enum):
    """Method used to extract document structure."""

    EPUB_NATIVE = "epub_native"
    PDF_OUTLINE = "pdf_outline"
    PDF_FONT = "pdf_font"
    PDF_PATTERN = "pdf_pattern"
    PDF_LAYOUT = "pdf_layout"
    PDF_PAGE_CHUNKS = "pdf_page_chunks"


class Section(BaseModel):
    """A detected section/chapter in the document."""

    title: str
    page_start: int | None = None
    page_end: int | None = None
    line_number: int | None = None
    level: int = 1
    confidence: float = 1.0
    pattern_type: str | None = None  # For pattern layer debugging


class DetectionResult(BaseModel):
    """Result from a detection layer."""

    sections: list[Section]
    method: ExtractionMethod
    confidence: float
    warnings: list[str] = Field(default_factory=list)
