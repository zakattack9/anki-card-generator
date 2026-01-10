# PRD: Multi-Format Book Extraction (EPUB + PDF)

## Overview

Extend `anki-gen parse` to support both EPUB and PDF formats using a unified extraction interface. PDF extraction uses a layered cascade approach that attempts progressively less reliable methods, exiting early when a reliable method succeeds.

## Current State

### Existing Architecture

```
cli.py
├── parse command → commands/parse.py
│   ├── EpubParser (core/epub_parser.py)
│   ├── OutputWriter (core/output_writer.py)
│   └── CacheManager (cache/manager.py)
```

### Existing Models

**`models/epub.py`**:
```python
class Chapter(BaseModel):
    id: str
    title: str
    index: int
    file_name: str
    raw_content: bytes = b""
    word_count: int = 0
    has_images: bool = False

class BookMetadata(BaseModel):
    title: str
    authors: list[str]
    language: str | None
    publisher: str | None
    publication_date: str | None

class ParsedEpub(BaseModel):
    metadata: BookMetadata
    toc: list[TOCEntry]
    chapters: list[Chapter]
    spine_order: list[str]
```

**`models/output.py`**:
```python
class ChapterMetadata(BaseModel):
    chapter_id: str
    chapter_index: int
    title: str
    source_file: str
    source_epub: str  # Needs renaming → source_path
    extracted_at: datetime
    word_count: int
    character_count: int
    paragraph_count: int

class BookOutput(BaseModel):
    book_title: str
    authors: list[str]
    total_chapters: int
    extracted_chapters: list[int]
    output_directory: str
    created_at: datetime
    chapters: list[ChapterMetadata]
```

### Current Limitations
- Only EPUB extraction supported via `EpubParser`
- `source_epub` field name assumes EPUB format
- No PDF support
- No format detection

## Proposed State

- Unified `BookParser` interface supporting multiple formats
- EPUB extraction unchanged (high reliability)
- PDF extraction via cascading detection layers
- Format auto-detection from file extension
- Consistent output format regardless of input type
- Confidence scoring for extracted structure
- Backward compatible model changes

---

## Architecture

### Proposed File Structure

```
core/
├── epub_parser.py      # Existing (implements BookParser)
├── pdf_parser.py       # New (implements BookParser)
├── parser_factory.py   # New (format detection + factory)
├── content_processor.py
├── output_writer.py    # Updated (format-agnostic)
└── flashcard_generator.py

models/
├── epub.py             # Existing (rename to book.py)
├── extraction.py       # New (confidence, detection method)
├── output.py           # Updated (source_epub → source_path)
└── flashcard.py
```

### Unified Interface

```python
# core/parser_factory.py

from abc import ABC, abstractmethod
from pathlib import Path

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
        '.epub': 'epub',
        '.pdf': 'pdf',
    }

    @classmethod
    def create(cls, path: Path) -> BookParser:
        """Create appropriate parser for the given file."""
        suffix = path.suffix.lower()

        if suffix not in cls.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {suffix}")

        if suffix == '.epub':
            from anki_gen.core.epub_parser import EpubParser
            return EpubParser(path)
        elif suffix == '.pdf':
            from anki_gen.core.pdf_parser import PdfParser
            return PdfParser(path)

    @classmethod
    def detect_format(cls, path: Path) -> str:
        """Detect file format from extension."""
        suffix = path.suffix.lower()
        return cls.SUPPORTED_FORMATS.get(suffix, 'unknown')
```

### PDF Cascade Layers

```
┌─────────────────────────────────────────────────────────┐
│                   PDF Section Detection                  │
├─────────────────────────────────────────────────────────┤
│  Layer 1: PDF Outline/Bookmarks     → Early exit if ≥2 entries
│  Layer 2: Font Size Analysis        → Early exit if confidence > 0.7
│  Layer 3: Regex Pattern Matching    → Early exit if ≥3 matches
│  Layer 4: Layout Heuristics         → No early exit (supplement)
│  Layer 5: Page-based chunking       → Final fallback
└─────────────────────────────────────────────────────────┘
```

---

## Cascade Detection Specification

### Layer Configuration

```python
# core/pdf_parser.py

from dataclasses import dataclass
from typing import Callable

@dataclass
class CascadeLayer:
    """Configuration for a detection layer."""
    name: str
    method: str  # ExtractionMethod enum value
    fn: Callable[[Path], DetectionResult | None]
    min_confidence: float
    early_exit: bool
    description: str

DETECTION_LAYERS: list[CascadeLayer] = [
    CascadeLayer(
        name='outline',
        method='pdf_outline',
        fn=detect_by_outline,
        min_confidence=0.90,
        early_exit=True,
        description='PDF bookmarks/outline'
    ),
    CascadeLayer(
        name='font',
        method='pdf_font',
        fn=detect_by_font,
        min_confidence=0.70,
        early_exit=True,
        description='Font size analysis'
    ),
    CascadeLayer(
        name='pattern',
        method='pdf_pattern',
        fn=detect_by_pattern,
        min_confidence=0.50,
        early_exit=True,
        description='Regex pattern matching'
    ),
    CascadeLayer(
        name='layout',
        method='pdf_layout',
        fn=detect_by_layout,
        min_confidence=0.35,
        early_exit=False,
        description='Layout heuristics'
    ),
]
```

---

### Layer 1: PDF Outline/Bookmarks

**Confidence**: 0.95
**Early Exit**: Yes (if outline has ≥2 entries)
**Dependency**: `pypdf`

```python
import pypdf
from pathlib import Path

def detect_by_outline(pdf_path: Path) -> DetectionResult | None:
    """
    Extract structure from PDF bookmarks/outline.
    Most reliable when present - maps directly to intended TOC.

    Returns None if no outline exists or outline has <2 entries.
    """
    reader = pypdf.PdfReader(str(pdf_path))

    if not reader.outline:
        return None

    sections = []

    def flatten_outline(items, level=0):
        """Recursively flatten nested outline."""
        for item in items:
            if isinstance(item, list):
                # Nested items
                flatten_outline(item, level + 1)
            else:
                # Destination object
                try:
                    page_num = reader.get_destination_page_number(item)
                    sections.append(Section(
                        title=item.title,
                        page_start=page_num,
                        level=level,
                        confidence=0.95,
                    ))
                except Exception:
                    # Skip malformed destinations
                    continue

    flatten_outline(reader.outline)

    if len(sections) >= 2:
        return DetectionResult(
            sections=sections,
            method=ExtractionMethod.PDF_OUTLINE,
            confidence=0.95,
        )

    return None
```

---

### Layer 2: Font Size Analysis

**Confidence**: 0.70-0.85
**Early Exit**: Yes (if avg confidence > 0.7)
**Dependency**: `pdfplumber`

```python
import pdfplumber
from collections import Counter
from pathlib import Path

def detect_by_font(pdf_path: Path) -> DetectionResult | None:
    """
    Detect headings via font size relative to body text.
    Larger/bolder text = likely heading.
    """
    with pdfplumber.open(str(pdf_path)) as pdf:
        # First pass: determine body text size (mode of font sizes)
        all_sizes = []
        for page in pdf.pages[:20]:  # Sample first 20 pages
            for char in page.chars:
                if char.get('size'):
                    all_sizes.append(round(char['size'], 1))

        if not all_sizes:
            return None

        # Body size = most common font size
        size_counts = Counter(all_sizes)
        body_size = size_counts.most_common(1)[0][0]

        # Second pass: find headings
        sections = []
        for page_num, page in enumerate(pdf.pages):
            lines = _extract_lines_from_page(page)

            for line in lines:
                confidence = _calculate_heading_confidence(line, body_size)

                if confidence >= 0.5:
                    sections.append(Section(
                        title=line['text'].strip(),
                        page_start=page_num,
                        level=_infer_level_from_size(line['size'], body_size),
                        confidence=min(confidence, 0.85),
                    ))

        # Deduplicate and filter
        sections = _dedupe_sections(sections)

        if sections and _avg_confidence(sections) > 0.7:
            return DetectionResult(
                sections=sections,
                method=ExtractionMethod.PDF_FONT,
                confidence=_avg_confidence(sections),
            )

    return None


def _calculate_heading_confidence(line: dict, body_size: float) -> float:
    """Calculate confidence that a line is a heading."""
    confidence = 0.0
    size_ratio = line['size'] / body_size if body_size else 1.0

    # Size-based scoring
    if size_ratio >= 1.5:
        confidence += 0.4
    elif size_ratio >= 1.3:
        confidence += 0.25
    elif size_ratio >= 1.15:
        confidence += 0.1

    # Bold detection
    fontname = line.get('fontname', '').lower()
    if 'bold' in fontname or 'heavy' in fontname:
        confidence += 0.2

    # All caps
    text = line['text'].strip()
    if text.isupper() and len(text) > 3:
        confidence += 0.1

    # Short line (headings rarely wrap)
    if len(text) < 80:
        confidence += 0.1

    # Exclude likely headers/footers
    if _is_likely_header_footer(line, text):
        confidence -= 0.5

    return max(0.0, confidence)


def _is_likely_header_footer(line: dict, text: str) -> bool:
    """Detect running headers/footers to exclude."""
    # Page numbers
    if text.strip().isdigit():
        return True
    # Very short repeated text
    if len(text) < 5:
        return True
    return False


def _infer_level_from_size(size: float, body_size: float) -> int:
    """Infer heading level from font size ratio."""
    ratio = size / body_size if body_size else 1.0
    if ratio >= 1.5:
        return 1
    elif ratio >= 1.3:
        return 2
    else:
        return 3


def _extract_lines_from_page(page) -> list[dict]:
    """Extract lines with font info from a pdfplumber page."""
    lines = []
    current_line = {'text': '', 'size': 0, 'fontname': '', 'top': 0, 'x0': 0}

    chars = sorted(page.chars, key=lambda c: (c['top'], c['x0']))

    for char in chars:
        # New line detection (vertical gap)
        if current_line['text'] and (char['top'] - current_line['top']) > 5:
            if current_line['text'].strip():
                lines.append(current_line)
            current_line = {
                'text': char['text'],
                'size': char.get('size', 12),
                'fontname': char.get('fontname', ''),
                'top': char['top'],
                'x0': char['x0'],
            }
        else:
            current_line['text'] += char['text']
            # Use largest font in line
            if char.get('size', 0) > current_line['size']:
                current_line['size'] = char['size']
                current_line['fontname'] = char.get('fontname', '')

    if current_line['text'].strip():
        lines.append(current_line)

    return lines
```

---

### Layer 3: Regex Pattern Matching

**Confidence**: 0.50-0.65
**Early Exit**: Yes (if ≥3 matches found)
**Dependencies**: None (stdlib `re`)

```python
import re
from pathlib import Path

# Patterns ordered by specificity (most specific first)
SECTION_PATTERNS: list[tuple[str, float, str]] = [
    # Chapter patterns (highest confidence)
    (r'^Chapter\s+(\d+)[:\s]', 0.65, 'chapter_num'),
    (r'^CHAPTER\s+(\d+)[:\s]', 0.65, 'chapter_num'),
    (r'^Chapter\s+([IVXLC]+)[:\s]', 0.60, 'chapter_roman'),
    (r'^CHAPTER\s+([IVXLC]+)[:\s]', 0.60, 'chapter_roman'),
    (r'^Chapter\s+(\w+)[:\s]', 0.55, 'chapter_word'),  # "Chapter One"

    # Part patterns
    (r'^Part\s+(\d+)[:\s]', 0.60, 'part_num'),
    (r'^PART\s+(\d+)[:\s]', 0.60, 'part_num'),
    (r'^Part\s+([IVXLC]+)[:\s]', 0.55, 'part_roman'),

    # Section patterns
    (r'^Section\s+(\d+)[:\.\s]', 0.55, 'section'),
    (r'^(\d+)\.\s+[A-Z][a-z]', 0.50, 'numbered'),      # "1. Introduction"
    (r'^(\d+\.\d+)\s+[A-Z]', 0.50, 'decimal'),         # "1.1 Overview"

    # Roman numeral standalone
    (r'^([IVXLC]+)\.\s+[A-Z]', 0.50, 'roman'),

    # Unit/Lesson (textbooks)
    (r'^Unit\s+(\d+)[:\s]', 0.55, 'unit'),
    (r'^Lesson\s+(\d+)[:\s]', 0.55, 'lesson'),
]


def detect_by_pattern(pdf_path: Path) -> DetectionResult | None:
    """
    Match common section/chapter patterns in text.
    Works well for consistently formatted textbooks.
    """
    text = _extract_full_text(pdf_path)
    lines = text.split('\n')

    sections = []
    seen_patterns: dict[str, list] = {}  # Track pattern sequences

    for line_num, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped or len(line_stripped) > 100:
            continue

        for pattern, base_confidence, pattern_type in SECTION_PATTERNS:
            match = re.match(pattern, line_stripped)
            if match:
                # Track for sequence detection
                if pattern_type not in seen_patterns:
                    seen_patterns[pattern_type] = []
                seen_patterns[pattern_type].append(match.group(1))

                sections.append(Section(
                    title=line_stripped,
                    line_number=line_num,
                    level=1 if 'part' in pattern_type else 2,
                    confidence=base_confidence,
                    pattern_type=pattern_type,
                ))
                break  # Only match first pattern per line

    # Boost confidence for sequential patterns (1, 2, 3... or I, II, III...)
    sections = _boost_sequential_confidence(sections, seen_patterns)

    # Need at least 3 matches to be meaningful
    if len(sections) >= 3:
        return DetectionResult(
            sections=sections,
            method=ExtractionMethod.PDF_PATTERN,
            confidence=_avg_confidence(sections),
        )

    return None


def _boost_sequential_confidence(
    sections: list[Section],
    seen_patterns: dict[str, list]
) -> list[Section]:
    """Boost confidence for patterns that form sequences."""
    for pattern_type, values in seen_patterns.items():
        if len(values) < 3:
            continue

        is_sequential = _check_sequence(values, pattern_type)
        if is_sequential:
            for section in sections:
                if getattr(section, 'pattern_type', None) == pattern_type:
                    section.confidence = min(section.confidence + 0.1, 0.75)

    return sections


def _check_sequence(values: list[str], pattern_type: str) -> bool:
    """Check if values form a logical sequence."""
    if 'roman' in pattern_type:
        # Convert Roman numerals
        try:
            nums = [_roman_to_int(v) for v in values]
            return nums == list(range(nums[0], nums[0] + len(nums)))
        except ValueError:
            return False
    elif pattern_type in ('chapter_num', 'part_num', 'section', 'numbered'):
        try:
            nums = [int(v) for v in values]
            return nums == list(range(nums[0], nums[0] + len(nums)))
        except ValueError:
            return False
    return False


def _roman_to_int(s: str) -> int:
    """Convert Roman numeral to integer."""
    values = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100}
    result = 0
    prev = 0
    for char in reversed(s.upper()):
        curr = values.get(char, 0)
        if curr < prev:
            result -= curr
        else:
            result += curr
        prev = curr
    return result


def _extract_full_text(pdf_path: Path) -> str:
    """Extract all text from PDF for pattern matching."""
    import pypdf
    reader = pypdf.PdfReader(str(pdf_path))
    text_parts = []
    for page in reader.pages:
        text_parts.append(page.extract_text() or '')
    return '\n'.join(text_parts)
```

---

### Layer 4: Layout Heuristics

**Confidence**: 0.30-0.50
**Early Exit**: No (supplements other layers)
**Dependency**: `pdfplumber`

```python
def detect_by_layout(pdf_path: Path) -> DetectionResult | None:
    """
    Use visual layout cues to detect section breaks.
    - Large vertical whitespace before
    - Near left margin
    - Short line length
    - Followed by body text
    """
    with pdfplumber.open(str(pdf_path)) as pdf:
        sections = []

        for page_num, page in enumerate(pdf.pages):
            lines = _extract_lines_with_positions(page)
            page_height = page.height

            for i, line in enumerate(lines):
                confidence = 0.0
                text = line['text'].strip()

                # Skip empty/short lines
                if not text or len(text) < 3:
                    continue

                # Vertical whitespace before (gap from previous line)
                if i > 0:
                    gap = line['top'] - lines[i-1]['bottom']
                    if gap > 40:
                        confidence += 0.25
                    elif gap > 25:
                        confidence += 0.15

                # Near left margin (within 15% of page width)
                if line['x0'] < page.width * 0.15:
                    confidence += 0.1

                # Short line (headings rarely wrap)
                if len(text) < 60:
                    confidence += 0.1

                # Near top of page (first 20%)
                if line['top'] < page_height * 0.2:
                    confidence += 0.1

                # Followed by text at different size (if detectable)
                if i < len(lines) - 1:
                    next_line = lines[i + 1]
                    if next_line.get('size', 12) < line.get('size', 12) * 0.9:
                        confidence += 0.15

                # Exclude likely page numbers, headers, footers
                if _is_page_number(text) or line['top'] > page_height * 0.9:
                    confidence = 0.0

                if confidence >= 0.35:
                    sections.append(Section(
                        title=text,
                        page_start=page_num,
                        level=1,
                        confidence=min(confidence, 0.50),
                    ))

        # Filter noise (remove duplicates, very short titles)
        sections = _filter_noise(sections)

        if sections:
            return DetectionResult(
                sections=sections,
                method=ExtractionMethod.PDF_LAYOUT,
                confidence=_avg_confidence(sections),
            )

    return None


def _is_page_number(text: str) -> bool:
    """Check if text is likely a page number."""
    text = text.strip()
    # Pure digits
    if text.isdigit():
        return True
    # Roman numerals (common for front matter)
    if re.match(r'^[ivxlc]+$', text.lower()):
        return True
    # "Page X" format
    if re.match(r'^page\s+\d+$', text.lower()):
        return True
    return False


def _filter_noise(sections: list[Section]) -> list[Section]:
    """Remove noisy detections."""
    filtered = []
    seen_titles = set()

    for section in sections:
        title_lower = section.title.lower().strip()

        # Skip duplicates
        if title_lower in seen_titles:
            continue

        # Skip very short titles (likely false positives)
        if len(title_lower) < 3:
            continue

        # Skip common false positives
        false_positives = {'contents', 'index', 'bibliography', 'references',
                         'acknowledgments', 'about the author', 'copyright'}
        if title_lower in false_positives and section.confidence < 0.5:
            continue

        seen_titles.add(title_lower)
        filtered.append(section)

    return filtered
```

---

### Layer 5: Page-Based Chunking (Fallback)

**Confidence**: 0.20
**Early Exit**: N/A (final fallback)

```python
def chunk_by_pages(
    pdf_path: Path,
    pages_per_chunk: int = 10
) -> DetectionResult:
    """
    Fallback: Split PDF into fixed-size page chunks.
    No structural detection - just ensures content is processable.

    Used when all detection layers fail.
    """
    import pypdf
    reader = pypdf.PdfReader(str(pdf_path))
    total_pages = len(reader.pages)

    sections = []
    chunk_num = 1

    for i in range(0, total_pages, pages_per_chunk):
        end_page = min(i + pages_per_chunk, total_pages)
        sections.append(Section(
            title=f"Section {chunk_num} (Pages {i+1}-{end_page})",
            page_start=i,
            page_end=end_page - 1,
            level=1,
            confidence=0.20,
        ))
        chunk_num += 1

    return DetectionResult(
        sections=sections,
        method=ExtractionMethod.PDF_PAGE_CHUNKS,
        confidence=0.20,
        warnings=['No document structure detected. Using page-based chunking.'],
    )
```

---

### Cascade Orchestrator

```python
# core/pdf_parser.py

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def detect_sections(pdf_path: Path) -> DetectionResult:
    """
    Run cascade detection with early termination.
    Returns first reliable result or falls back to page chunks.
    """
    for layer in DETECTION_LAYERS:
        log.info(f"Trying detection layer: {layer.name} ({layer.description})")

        try:
            result = layer.fn(pdf_path)
        except Exception as e:
            log.warning(f"Layer {layer.name} failed with error: {e}")
            continue

        if result is None:
            log.info(f"  Layer {layer.name}: No results")
            continue

        if result.confidence >= layer.min_confidence:
            log.info(
                f"  Layer {layer.name}: SUCCESS - "
                f"{len(result.sections)} sections, "
                f"confidence={result.confidence:.2f}"
            )

            if layer.early_exit:
                log.info(f"  Early exit triggered at layer: {layer.name}")
                return result
        else:
            log.info(
                f"  Layer {layer.name}: Below threshold - "
                f"confidence={result.confidence:.2f} < {layer.min_confidence}"
            )

    # All layers exhausted, use fallback
    log.warning("All detection layers failed. Using page-based chunking.")
    return chunk_by_pages(pdf_path)
```

---

## Data Models

### New Models (`models/extraction.py`)

```python
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
```

### Updated Models

**`models/epub.py` → `models/book.py`** (rename for generality):

```python
class Chapter(BaseModel):
    """Chapter content and metadata."""
    id: str
    title: str
    index: int
    file_name: str  # or page range for PDF
    raw_content: bytes = b""
    word_count: int = 0
    has_images: bool = False
    # New fields for PDF support
    page_start: int | None = None
    page_end: int | None = None
    extraction_confidence: float = 1.0
    extraction_method: ExtractionMethod = ExtractionMethod.EPUB_NATIVE


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

# Alias for backward compatibility
ParsedEpub = ParsedBook
```

**`models/output.py`** (updated):

```python
class ChapterMetadata(BaseModel):
    """Metadata accompanying chapter content."""
    chapter_id: str
    chapter_index: int
    title: str
    source_file: str
    source_path: str  # Renamed from source_epub
    extracted_at: datetime
    word_count: int
    character_count: int
    paragraph_count: int
    # New fields
    page_start: int | None = None
    page_end: int | None = None
    extraction_confidence: float = 1.0
    extraction_method: str = "epub_native"


class BookOutput(BaseModel):
    """Complete book output manifest."""
    book_title: str
    authors: list[str]
    total_chapters: int
    extracted_chapters: list[int]
    output_directory: str
    created_at: datetime
    chapters: list[ChapterMetadata]
    # New fields
    source_format: str = "epub"
    extraction_method: str = "epub_native"
    extraction_confidence: float = 1.0
    warnings: list[str] = Field(default_factory=list)
```

---

## PDF Parser Implementation

### Complete PdfParser Class

```python
# core/pdf_parser.py

import logging
from pathlib import Path

import pypdf
import pdfplumber

from anki_gen.models.book import BookMetadata, Chapter, ParsedBook, TOCEntry
from anki_gen.models.extraction import DetectionResult, ExtractionMethod, Section

log = logging.getLogger(__name__)


class PdfParser:
    """Parse PDF files and extract structure using cascade detection."""

    def __init__(self, pdf_path: Path):
        self.path = pdf_path
        self._reader = pypdf.PdfReader(str(pdf_path))
        self._detection_result: DetectionResult | None = None

    def parse(self) -> ParsedBook:
        """Parse the PDF and return complete structure."""
        # Run cascade detection
        self._detection_result = detect_sections(self.path)

        # Extract content for each detected section
        chapters = self._extract_chapters()

        return ParsedBook(
            metadata=self._get_metadata(),
            toc=self._build_toc(),
            chapters=chapters,
            spine_order=[],  # N/A for PDF
            source_format="pdf",
            extraction_method=self._detection_result.method,
            extraction_confidence=self._detection_result.confidence,
            warnings=self._detection_result.warnings,
        )

    def _get_metadata(self) -> BookMetadata:
        """Extract book metadata from PDF."""
        info = self._reader.metadata or {}

        return BookMetadata(
            title=info.get('/Title', self.path.stem) or self.path.stem,
            authors=[info.get('/Author', '')] if info.get('/Author') else [],
            language=None,  # Not standard in PDF metadata
            publisher=info.get('/Producer', None),
            publication_date=info.get('/CreationDate', None),
        )

    def _build_toc(self) -> list[TOCEntry]:
        """Build TOC from detected sections."""
        if not self._detection_result:
            return []

        entries = []
        for i, section in enumerate(self._detection_result.sections):
            entries.append(TOCEntry(
                id=f"section_{i+1:03d}",
                title=section.title,
                href=f"page_{section.page_start or 0}",
                level=section.level,
                children=[],
            ))
        return entries

    def _extract_chapters(self) -> list[Chapter]:
        """Extract content for each detected section."""
        if not self._detection_result:
            return []

        chapters = []
        sections = self._detection_result.sections

        for i, section in enumerate(sections):
            # Determine page range
            page_start = section.page_start or 0
            if section.page_end is not None:
                page_end = section.page_end
            elif i + 1 < len(sections):
                # End at next section's start
                next_start = sections[i + 1].page_start or page_start
                page_end = max(page_start, next_start - 1)
            else:
                # Last section: go to end of document
                page_end = len(self._reader.pages) - 1

            # Extract text content
            content = self._extract_page_range(page_start, page_end)

            chapters.append(Chapter(
                id=f"chapter_{i+1:03d}",
                title=section.title,
                index=i,
                file_name=f"pages_{page_start+1}-{page_end+1}",
                raw_content=content.encode('utf-8'),
                word_count=len(content.split()),
                has_images=False,  # TODO: Image detection
                page_start=page_start,
                page_end=page_end,
                extraction_confidence=section.confidence,
                extraction_method=self._detection_result.method,
            ))

        return chapters

    def _extract_page_range(self, start: int, end: int) -> str:
        """Extract text from a range of pages."""
        text_parts = []
        for page_num in range(start, end + 1):
            if page_num < len(self._reader.pages):
                page = self._reader.pages[page_num]
                text_parts.append(page.extract_text() or '')
        return '\n\n'.join(text_parts)


# Include all helper functions from layers above...
```

---

## Implementation Plan

### Phase 1: Model Updates (Non-Breaking)

**Files**: `models/epub.py`, `models/output.py`

- [ ] Add new fields to `Chapter` model (with defaults)
- [ ] Add new fields to `ChapterMetadata` (with defaults)
- [ ] Add new fields to `BookOutput` (with defaults)
- [ ] Add `source_path` field (deprecate `source_epub` later)
- [ ] Create `models/extraction.py` with new models
- [ ] Add backward compatibility aliases

### Phase 2: Create Parser Factory

**File**: `core/parser_factory.py` (new)

- [ ] Create `BookParser` abstract base class
- [ ] Create `ParserFactory.create()` method
- [ ] Create `ParserFactory.detect_format()` method
- [ ] Add format validation

### Phase 3: Refactor EpubParser

**File**: `core/epub_parser.py`

- [ ] Implement `BookParser` interface
- [ ] Return `ParsedBook` instead of `ParsedEpub`
- [ ] Set `source_format = "epub"`
- [ ] Set `extraction_method = EPUB_NATIVE`
- [ ] Set `extraction_confidence = 1.0`
- [ ] Maintain backward compatibility

### Phase 4: PDF Parser - Core Structure

**File**: `core/pdf_parser.py` (new)

- [ ] Create `PdfParser` class skeleton
- [ ] Implement `parse()` method
- [ ] Implement `_get_metadata()` method
- [ ] Implement `_build_toc()` method
- [ ] Implement `_extract_chapters()` method
- [ ] Implement `_extract_page_range()` method

### Phase 5: PDF Parser - Layer 1 (Outline)

**File**: `core/pdf_parser.py`

- [ ] Implement `detect_by_outline()` function
- [ ] Handle nested outlines
- [ ] Handle malformed destinations
- [ ] Add unit tests

### Phase 6: PDF Parser - Layer 2 (Font)

**File**: `core/pdf_parser.py`

- [ ] Implement `detect_by_font()` function
- [ ] Implement `_extract_lines_from_page()` helper
- [ ] Implement `_calculate_heading_confidence()` helper
- [ ] Implement header/footer detection
- [ ] Add unit tests

### Phase 7: PDF Parser - Layer 3 (Pattern)

**File**: `core/pdf_parser.py`

- [ ] Implement `detect_by_pattern()` function
- [ ] Add all pattern definitions
- [ ] Implement sequence detection
- [ ] Implement Roman numeral conversion
- [ ] Add unit tests

### Phase 8: PDF Parser - Layer 4 (Layout)

**File**: `core/pdf_parser.py`

- [ ] Implement `detect_by_layout()` function
- [ ] Implement position-based scoring
- [ ] Implement noise filtering
- [ ] Add unit tests

### Phase 9: PDF Parser - Layer 5 (Fallback)

**File**: `core/pdf_parser.py`

- [ ] Implement `chunk_by_pages()` function
- [ ] Add configurable chunk size
- [ ] Add unit tests

### Phase 10: Cascade Orchestrator

**File**: `core/pdf_parser.py`

- [ ] Define `DETECTION_LAYERS` configuration
- [ ] Implement `detect_sections()` orchestrator
- [ ] Add logging for detection flow
- [ ] Add unit tests for cascade behavior

### Phase 11: Update OutputWriter

**File**: `core/output_writer.py`

- [ ] Update `ChapterMetadata` population
- [ ] Add `source_format` to manifest
- [ ] Add `extraction_method` to manifest
- [ ] Add `extraction_confidence` to manifest
- [ ] Add per-chapter confidence scores
- [ ] Handle `source_path` field

### Phase 12: Update Parse Command

**File**: `commands/parse.py`

- [ ] Use `ParserFactory.create()` instead of `EpubParser`
- [ ] Update file extension validation
- [ ] Add detection method to output display
- [ ] Add confidence warnings in output
- [ ] Update cache key generation for PDFs

### Phase 13: CLI Updates

**File**: `cli.py`

- [ ] Update `epub_path` argument → `book_path`
- [ ] Accept `.epub` and `.pdf` extensions
- [ ] Add `--format` option (auto|epub|pdf)
- [ ] Add `--pdf-method` option to force specific layer
- [ ] Add `--chunk-size` option for fallback
- [ ] Update help text

### Phase 14: Cache Updates

**File**: `cache/manager.py`

- [ ] Support PDF caching
- [ ] Include extraction method in cache key
- [ ] Handle cache invalidation for method changes

---

## CLI Changes

### Updated Command Signature

```bash
# Auto-detect format (default behavior)
anki-gen parse book.epub
anki-gen parse book.pdf

# Force specific format
anki-gen parse book.pdf --format pdf

# Force specific PDF detection method (skip cascade)
anki-gen parse book.pdf --pdf-method outline
anki-gen parse book.pdf --pdf-method font
anki-gen parse book.pdf --pdf-method pattern
anki-gen parse book.pdf --pdf-method layout
anki-gen parse book.pdf --pdf-method page_chunks

# Configure page chunk size (for fallback)
anki-gen parse book.pdf --chunk-size 15

# Add custom section pattern (appends to built-in patterns)
anki-gen parse book.pdf --pattern "^Lesson\s+\d+"
```

### Output Display

```
$ anki-gen parse textbook.pdf

Parsing: textbook.pdf
Format: PDF
Detecting structure...
  Layer 1 (outline): No bookmarks found
  Layer 2 (font): 12 sections (confidence: 0.78) ✓

┌─ Book Info ─────────────────────────────────┐
│ Introduction to Economics                    │
│ Author(s): Paul Krugman                      │
│ Chapters: 12                                 │
│ Method: pdf_font (confidence: 0.78)          │
└──────────────────────────────────────────────┘

┌─ Table of Contents ─────────────────────────┐
│ #   Title                          Words    │
│ 1   Introduction                   3,421    │
│ 2   Supply and Demand              5,892    │
│ ...                                         │
└──────────────────────────────────────────────┘

Select chapters to extract:
  - Enter chapter numbers (e.g., 1,3,5-7)
  - Enter all for all chapters
  - Enter q to quit

Your selection: all

Extracting chapters... ━━━━━━━━━━ 12/12
✓ Successfully extracted 12 chapter(s)

  Output directory: textbook_chapters/
  Manifest: manifest.json
  Extraction method: pdf_font
  Average confidence: 0.78

  ⚠ Lower confidence sections:
    - Chapter 7: "Market Equilibrium" (0.52)
```

---

## Dependencies

### Required Dependencies

```toml
# pyproject.toml additions
[project.dependencies]
pypdf = ">=4.0,<5.0"         # PDF reading, outline extraction, text extraction
pdfplumber = ">=0.10,<1.0"   # Layout analysis, font extraction, positioning
```

### Installation

```bash
# Update existing install
pip install anki-gen[pdf]

# Or install dependencies directly
pip install pypdf pdfplumber
```

---

## Confidence Thresholds Summary

| Layer | Method | Min Confidence | Early Exit | Typical Range |
|-------|--------|---------------|------------|---------------|
| 1 | Outline/Bookmarks | 0.90 | Yes | 0.95 |
| 2 | Font Size | 0.70 | Yes | 0.70-0.85 |
| 3 | Pattern Matching | 0.50 | Yes | 0.50-0.65 |
| 4 | Layout Heuristics | 0.35 | No | 0.30-0.50 |
| 5 | Page Chunks | N/A | N/A | 0.20 (fixed) |

---

## Edge Cases & Error Handling

| Scenario | Detection | Handling |
|----------|-----------|----------|
| Scanned PDF (image-only) | Text extraction returns empty | Error: "PDF appears to be scanned. OCR required." |
| Encrypted PDF | pypdf raises `PdfReadError` | Error: "PDF is encrypted. Please decrypt first." |
| Empty PDF | 0 pages | Error: "PDF has no pages." |
| Corrupted PDF | pypdf raises exception | Error: "PDF appears corrupted: {error}" |
| Very large PDF (>1000 pages) | Detect page count | Warning + increased chunk size |
| No sections found | All layers return None | Use page chunks + warning |
| Mixed font sizes | Body size detection | Use mode (most common size) |
| Multi-column layout | Affects text extraction | Handled by pdfplumber |
| Non-English text | Pattern matching | Patterns may not match |
| Tables/figures | May detect as sections | Filter short titles in layout layer |

---

## Testing Checklist

### Unit Tests

- [ ] `detect_by_outline()` with nested bookmarks
- [ ] `detect_by_outline()` with empty outline
- [ ] `detect_by_font()` with various size ratios
- [ ] `detect_by_font()` header/footer exclusion
- [ ] `detect_by_pattern()` for all pattern types
- [ ] `detect_by_pattern()` sequence detection
- [ ] `detect_by_layout()` whitespace scoring
- [ ] `chunk_by_pages()` with various sizes
- [ ] Cascade early termination at each layer
- [ ] Confidence calculation accuracy

### Integration Tests

- [ ] EPUB parsing unchanged
- [ ] PDF with bookmarks → Layer 1 exit
- [ ] PDF without bookmarks → Layer 2+ cascade
- [ ] PDF with "Chapter X" format → Layer 3 exit
- [ ] Unstructured PDF → Page chunks fallback
- [ ] Manifest generation with confidence
- [ ] Cache hit/miss for PDFs
- [ ] Mixed batch (EPUB + PDF)

### Manual Testing

- [ ] Textbook with clear chapters
- [ ] Novel with part/chapter structure
- [ ] Technical manual with numbered sections
- [ ] Academic paper (less structured)
- [ ] Magazine/journal format
- [ ] Scanned PDF (should error gracefully)
- [ ] Very large PDF (>500 pages)

---

## Migration Notes

### Backward Compatibility

- `ParsedEpub` aliased to `ParsedBook`
- `source_epub` field still works (deprecated)
- Existing EPUB parsing unchanged
- Existing cache entries remain valid

### Breaking Changes

- None in Phase 1-13
- Phase 14: `epub_path` CLI argument renamed to `book_path`
  - Workaround: Both names accepted during transition

---

## Future Enhancements (Out of Scope)

- [ ] OCR integration for scanned PDFs (`pytesseract`, `pdf2image`)
- [ ] Table of Contents page parsing (visual TOC detection)
- [ ] Machine learning section classifier
- [ ] Custom pattern configuration file (`.anki-gen-patterns.yaml`)
- [ ] Hybrid mode (combine results from multiple layers)
- [ ] PDF form field extraction
- [ ] Annotation/highlight extraction
- [ ] Image extraction from PDFs
- [ ] Parallel page processing for large PDFs
