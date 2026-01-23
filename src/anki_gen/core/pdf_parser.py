"""PDF parsing with cascade structure detection."""

import logging
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Suppress warnings about malformed PDF object references from PDF libraries
logging.getLogger("pdfminer").setLevel(logging.ERROR)
logging.getLogger("pypdf").setLevel(logging.ERROR)

import pdfplumber
import pypdf
from pypdf.errors import EmptyFileError, FileNotDecryptedError, PdfReadError

from anki_gen.core.parser_factory import BookParser
from anki_gen.models.book import BookMetadata, Chapter, ParsedBook, TOCEntry
from anki_gen.models.extraction import DetectionResult, ExtractionMethod, Section

log = logging.getLogger(__name__)


# =============================================================================
# Cascade Layer Configuration
# =============================================================================


@dataclass
class CascadeLayer:
    """Configuration for a detection layer."""

    name: str
    method: ExtractionMethod
    fn: Callable[[Path], DetectionResult | None]
    min_confidence: float
    early_exit: bool
    description: str


# =============================================================================
# Layer 1: PDF Outline/Bookmarks
# =============================================================================


def detect_by_outline(pdf_path: Path) -> DetectionResult | None:
    """
    Extract structure from PDF bookmarks/outline.
    Most reliable when present - maps directly to intended TOC.

    Returns None if no outline exists or outline has <2 entries.
    """
    reader = pypdf.PdfReader(str(pdf_path))

    if not reader.outline:
        return None

    sections: list[Section] = []

    def flatten_outline(items: list, level: int = 0) -> None:
        """Recursively flatten nested outline."""
        for item in items:
            if isinstance(item, list):
                # Nested items
                flatten_outline(item, level + 1)
            else:
                # Destination object
                try:
                    page_num = reader.get_destination_page_number(item)
                    sections.append(
                        Section(
                            title=item.title,
                            page_start=page_num,
                            level=level,
                            confidence=0.95,
                        )
                    )
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


# =============================================================================
# Layer 2: Font Size Analysis
# =============================================================================


def detect_by_font(pdf_path: Path) -> DetectionResult | None:
    """
    Detect headings via font size relative to body text.
    Larger/bolder text = likely heading.
    """
    with pdfplumber.open(str(pdf_path)) as pdf:
        # First pass: determine body text size (mode of font sizes)
        all_sizes: list[float] = []
        sample_pages = min(20, len(pdf.pages))

        for page in pdf.pages[:sample_pages]:
            if page.chars:
                for char in page.chars:
                    if char.get("size"):
                        all_sizes.append(round(char["size"], 1))

        if not all_sizes:
            return None

        # Body size = most common font size
        size_counts = Counter(all_sizes)
        body_size = size_counts.most_common(1)[0][0]

        # Second pass: find headings
        sections: list[Section] = []
        for page_num, page in enumerate(pdf.pages):
            lines = _extract_lines_from_page(page)

            for line in lines:
                confidence = _calculate_heading_confidence(line, body_size)

                if confidence >= 0.5:
                    sections.append(
                        Section(
                            title=line["text"].strip(),
                            page_start=page_num,
                            level=_infer_level_from_size(line["size"], body_size),
                            confidence=min(confidence, 0.85),
                        )
                    )

        # Deduplicate and filter noise
        sections = _dedupe_sections(sections)
        sections = _filter_noise(sections)

        if sections and _avg_confidence(sections) > 0.7:
            return DetectionResult(
                sections=sections,
                method=ExtractionMethod.PDF_FONT,
                confidence=_avg_confidence(sections),
            )

    return None


def _extract_lines_from_page(page) -> list[dict]:
    """Extract lines with font info from a pdfplumber page."""
    lines = []

    if not page.chars:
        return lines

    current_line = {"text": "", "size": 0, "fontname": "", "top": 0, "x0": 0}
    chars = sorted(page.chars, key=lambda c: (c["top"], c["x0"]))

    for char in chars:
        # New line detection (vertical gap)
        if current_line["text"] and (char["top"] - current_line["top"]) > 5:
            if current_line["text"].strip():
                lines.append(current_line)
            current_line = {
                "text": char.get("text", ""),
                "size": char.get("size", 12),
                "fontname": char.get("fontname", ""),
                "top": char["top"],
                "x0": char["x0"],
            }
        else:
            current_line["text"] += char.get("text", "")
            # Use largest font in line
            if char.get("size", 0) > current_line["size"]:
                current_line["size"] = char["size"]
                current_line["fontname"] = char.get("fontname", "")

    if current_line["text"].strip():
        lines.append(current_line)

    return lines


def _calculate_heading_confidence(line: dict, body_size: float) -> float:
    """Calculate confidence that a line is a heading."""
    confidence = 0.0
    size_ratio = line["size"] / body_size if body_size else 1.0

    # Size-based scoring
    if size_ratio >= 1.5:
        confidence += 0.4
    elif size_ratio >= 1.3:
        confidence += 0.25
    elif size_ratio >= 1.15:
        confidence += 0.1

    # Bold detection
    fontname = line.get("fontname", "").lower()
    if "bold" in fontname or "heavy" in fontname:
        confidence += 0.2

    # All caps
    text = line["text"].strip()
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
    """Detect running headers/footers and non-content text to exclude."""
    text = text.strip()
    text_lower = text.lower()
    
    # Page numbers
    if text.isdigit():
        return True
    # Very short repeated text
    if len(text) < 5:
        return True
    
    # Social media handles (starting with @)
    if text.startswith("@"):
        return True
    
    # URLs and website-like text
    if text_lower.startswith(("http://", "https://", "www.")):
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


# =============================================================================
# Layer 3: Regex Pattern Matching
# =============================================================================

# Patterns ordered by specificity (most specific first)
SECTION_PATTERNS: list[tuple[str, float, str]] = [
    # Chapter patterns (highest confidence)
    (r"^Chapter\s+(\d+)[:\s]", 0.65, "chapter_num"),
    (r"^CHAPTER\s+(\d+)[:\s]", 0.65, "chapter_num"),
    (r"^Chapter\s+([IVXLC]+)[:\s]", 0.60, "chapter_roman"),
    (r"^CHAPTER\s+([IVXLC]+)[:\s]", 0.60, "chapter_roman"),
    (r"^Chapter\s+(\w+)[:\s]", 0.55, "chapter_word"),  # "Chapter One"
    # Part patterns
    (r"^Part\s+(\d+)[:\s]", 0.60, "part_num"),
    (r"^PART\s+(\d+)[:\s]", 0.60, "part_num"),
    (r"^Part\s+([IVXLC]+)[:\s]", 0.55, "part_roman"),
    # Article patterns (legal documents)
    (r"^Article\s+(\d+)[:\.\s]", 0.60, "article"),
    (r"^ARTICLE\s+(\d+)[:\.\s]", 0.60, "article"),
    (r"^Article\s+([IVXLC]+)[:\.\s]", 0.55, "article_roman"),
    # Section patterns
    (r"^Section\s+(\d+)[:\.\s]", 0.55, "section"),
    (r"^SECTION\s+(\d+)[:\.\s]", 0.55, "section"),
    # Numbered sections (various formats)
    (r"^(\d+)\.\s+[A-Z][a-z]", 0.50, "numbered"),  # "1. Introduction"
    (r"^(\d+)\s+[A-Z]{2,}", 0.55, "numbered_allcaps"),  # "1 DEFINITIONS"
    (r"^(\d+\.\d+)\s+[A-Z]", 0.50, "decimal"),  # "1.1 Overview"
    # Roman numeral standalone
    (r"^([IVXLC]+)\.\s+[A-Z]", 0.50, "roman"),
    # Unit/Lesson (textbooks)
    (r"^Unit\s+(\d+)[:\s]", 0.55, "unit"),
    (r"^Lesson\s+(\d+)[:\s]", 0.55, "lesson"),
]


def detect_by_pattern(pdf_path: Path) -> DetectionResult | None:
    """
    Match common section/chapter patterns in text.
    Works well for consistently formatted textbooks.
    """
    # Extract text with page boundaries for line-to-page mapping
    reader = pypdf.PdfReader(str(pdf_path))
    line_to_page: dict[int, int] = {}
    all_lines: list[str] = []
    current_line = 0

    for page_num, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        page_lines = page_text.split("\n")
        for _ in page_lines:
            line_to_page[current_line] = page_num
            current_line += 1
        all_lines.extend(page_lines)

    sections: list[Section] = []
    seen_patterns: dict[str, list] = {}  # Track pattern sequences

    for line_num, line in enumerate(all_lines):
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

                sections.append(
                    Section(
                        title=line_stripped,
                        page_start=line_to_page.get(line_num, 0),
                        line_number=line_num,
                        level=1 if "part" in pattern_type else 2,
                        confidence=base_confidence,
                        pattern_type=pattern_type,
                    )
                )
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
    sections: list[Section], seen_patterns: dict[str, list]
) -> list[Section]:
    """Boost confidence for patterns that form sequences."""
    for pattern_type, values in seen_patterns.items():
        if len(values) < 3:
            continue

        is_sequential = _check_sequence(values, pattern_type)
        if is_sequential:
            for section in sections:
                if getattr(section, "pattern_type", None) == pattern_type:
                    section.confidence = min(section.confidence + 0.1, 0.75)

    return sections


def _check_sequence(values: list[str], pattern_type: str) -> bool:
    """Check if values form a logical sequence."""
    if "roman" in pattern_type:
        # Convert Roman numerals
        try:
            nums = [_roman_to_int(v) for v in values]
            return nums == list(range(nums[0], nums[0] + len(nums)))
        except ValueError:
            return False
    elif pattern_type in (
        "chapter_num",
        "part_num",
        "section",
        "numbered",
        "numbered_allcaps",
        "article",
    ):
        try:
            nums = [int(v) for v in values]
            return nums == list(range(nums[0], nums[0] + len(nums)))
        except ValueError:
            return False
    return False


def _roman_to_int(s: str) -> int:
    """Convert Roman numeral to integer."""
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
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
    reader = pypdf.PdfReader(str(pdf_path))
    text_parts = []
    for page in reader.pages:
        text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts)


# =============================================================================
# Layer 4: Layout Heuristics
# =============================================================================


def detect_by_layout(pdf_path: Path) -> DetectionResult | None:
    """
    Use visual layout cues to detect section breaks.
    - Large vertical whitespace before
    - Near left margin
    - Short line length
    - Followed by body text
    """
    with pdfplumber.open(str(pdf_path)) as pdf:
        sections: list[Section] = []

        for page_num, page in enumerate(pdf.pages):
            lines = _extract_lines_with_positions(page)
            page_height = page.height

            for i, line in enumerate(lines):
                confidence = 0.0
                text = line["text"].strip()

                # Skip empty/short lines
                if not text or len(text) < 3:
                    continue

                # Vertical whitespace before (gap from previous line)
                if i > 0:
                    gap = line["top"] - lines[i - 1]["bottom"]
                    if gap > 40:
                        confidence += 0.25
                    elif gap > 25:
                        confidence += 0.15

                # Near left margin (within 15% of page width)
                if line["x0"] < page.width * 0.15:
                    confidence += 0.1

                # Short line (headings rarely wrap)
                if len(text) < 60:
                    confidence += 0.1

                # Near top of page (first 20%)
                if line["top"] < page_height * 0.2:
                    confidence += 0.1

                # Followed by text at different size (if detectable)
                if i < len(lines) - 1:
                    next_line = lines[i + 1]
                    if next_line.get("size", 12) < line.get("size", 12) * 0.9:
                        confidence += 0.15

                # Exclude likely page numbers, headers, footers
                if _is_page_number(text) or line["top"] > page_height * 0.9:
                    confidence = 0.0

                if confidence >= 0.35:
                    sections.append(
                        Section(
                            title=text,
                            page_start=page_num,
                            level=1,
                            confidence=min(confidence, 0.50),
                        )
                    )

        # Filter noise (remove duplicates, very short titles)
        sections = _filter_noise(sections)

        if sections:
            return DetectionResult(
                sections=sections,
                method=ExtractionMethod.PDF_LAYOUT,
                confidence=_avg_confidence(sections),
            )

    return None


def _extract_lines_with_positions(page) -> list[dict]:
    """Extract lines with position info from a pdfplumber page."""
    lines = []

    if not page.chars:
        return lines

    current_line = {
        "text": "",
        "size": 0,
        "top": 0,
        "bottom": 0,
        "x0": 0,
    }

    chars = sorted(page.chars, key=lambda c: (c["top"], c["x0"]))

    for char in chars:
        # New line detection (vertical gap)
        if current_line["text"] and (char["top"] - current_line["top"]) > 5:
            if current_line["text"].strip():
                lines.append(current_line)
            current_line = {
                "text": char.get("text", ""),
                "size": char.get("size", 12),
                "top": char["top"],
                "bottom": char["bottom"],
                "x0": char["x0"],
            }
        else:
            current_line["text"] += char.get("text", "")
            current_line["bottom"] = max(
                current_line.get("bottom", 0), char.get("bottom", 0)
            )
            if char.get("size", 0) > current_line["size"]:
                current_line["size"] = char["size"]

    if current_line["text"].strip():
        lines.append(current_line)

    return lines


def _is_page_number(text: str) -> bool:
    """Check if text is likely a page number."""
    text = text.strip()
    # Pure digits
    if text.isdigit():
        return True
    # Roman numerals (common for front matter)
    if re.match(r"^[ivxlc]+$", text.lower()):
        return True
    # "Page X" format
    if re.match(r"^page\s+\d+$", text.lower()):
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

        # Skip social media handles (starting with @)
        if section.title.strip().startswith("@"):
            continue

        # Skip common false positives
        false_positives = {
            "contents",
            "index",
            "bibliography",
            "references",
            "acknowledgments",
            "about the author",
            "copyright",
        }
        if title_lower in false_positives and section.confidence < 0.5:
            continue

        seen_titles.add(title_lower)
        filtered.append(section)

    return filtered


def _validate_section_distribution(
    sections: list[Section], pdf_path: Path, min_word_threshold: int = 50
) -> bool:
    """
    Check if word distribution across sections is healthy.
    Returns True if distribution seems valid, False if it suggests failed detection.

    Suspicious pattern: Many sections with very few words + 1-2 sections with
    almost all the content indicates the detection picked up noise (branding,
    headers) rather than actual chapter structure.
    """
    if len(sections) < 3:
        return True  # Too few sections to validate distribution

    # Calculate word counts for each section
    with pdfplumber.open(str(pdf_path)) as pdf:
        word_counts = []
        for i, section in enumerate(sections):
            page_start = section.page_start or 0
            if section.page_end is not None:
                page_end = section.page_end
            elif i + 1 < len(sections):
                page_end = max(page_start, (sections[i + 1].page_start or page_start) - 1)
            else:
                page_end = len(pdf.pages) - 1

            # Extract text and count words
            text_parts = []
            for page_num in range(page_start, min(page_end + 1, len(pdf.pages))):
                text_parts.append(pdf.pages[page_num].extract_text() or "")
            word_count = len(" ".join(text_parts).split())
            word_counts.append(word_count)

    total_words = sum(word_counts)
    if total_words == 0:
        return True  # No content to validate

    # Check for suspicious distribution:
    # If >60% of sections have <min_word_threshold words AND
    # top 2 sections contain >85% of total content
    tiny_sections = sum(1 for count in word_counts if count < min_word_threshold)
    tiny_ratio = tiny_sections / len(word_counts)

    sorted_counts = sorted(word_counts, reverse=True)
    top_two_ratio = sum(sorted_counts[:2]) / total_words if total_words > 0 else 0

    if tiny_ratio > 0.6 and top_two_ratio > 0.85:
        log.info(
            f"  Distribution check: {tiny_ratio:.0%} tiny sections, "
            f"{top_two_ratio:.0%} content in top 2 - suspicious"
        )
        return False  # Suspicious distribution

    return True


# =============================================================================
# Layer 5: Page-Based Chunking (Fallback)
# =============================================================================


def chunk_by_pages(pdf_path: Path, pages_per_chunk: int = 10) -> DetectionResult:
    """
    Fallback: Split PDF into fixed-size page chunks.
    No structural detection - just ensures content is processable.

    Used when all detection layers fail.
    """
    reader = pypdf.PdfReader(str(pdf_path))
    total_pages = len(reader.pages)

    sections: list[Section] = []
    chunk_num = 1

    for i in range(0, total_pages, pages_per_chunk):
        end_page = min(i + pages_per_chunk, total_pages)
        sections.append(
            Section(
                title=f"Section {chunk_num} (Pages {i + 1}-{end_page})",
                page_start=i,
                page_end=end_page - 1,
                level=1,
                confidence=0.20,
            )
        )
        chunk_num += 1

    return DetectionResult(
        sections=sections,
        method=ExtractionMethod.PDF_PAGE_CHUNKS,
        confidence=0.20,
        warnings=["No document structure detected. Using page-based chunking."],
    )


# =============================================================================
# Helper Functions
# =============================================================================


def _dedupe_sections(sections: list[Section]) -> list[Section]:
    """Remove duplicate sections based on title and page."""
    seen = set()
    deduped = []

    for section in sections:
        key = (section.title.lower().strip(), section.page_start)
        if key not in seen:
            seen.add(key)
            deduped.append(section)

    return deduped


def _avg_confidence(sections: list[Section]) -> float:
    """Calculate average confidence across sections."""
    if not sections:
        return 0.0
    return sum(s.confidence for s in sections) / len(sections)


# =============================================================================
# Cascade Orchestrator
# =============================================================================

# Detection layers in priority order
DETECTION_LAYERS: list[CascadeLayer] = [
    CascadeLayer(
        name="outline",
        method=ExtractionMethod.PDF_OUTLINE,
        fn=detect_by_outline,
        min_confidence=0.90,
        early_exit=True,
        description="PDF bookmarks/outline",
    ),
    CascadeLayer(
        name="font",
        method=ExtractionMethod.PDF_FONT,
        fn=detect_by_font,
        min_confidence=0.70,
        early_exit=True,
        description="Font size analysis",
    ),
    CascadeLayer(
        name="pattern",
        method=ExtractionMethod.PDF_PATTERN,
        fn=detect_by_pattern,
        min_confidence=0.50,
        early_exit=True,
        description="Regex pattern matching",
    ),
    CascadeLayer(
        name="layout",
        method=ExtractionMethod.PDF_LAYOUT,
        fn=detect_by_layout,
        min_confidence=0.35,
        early_exit=False,
        description="Layout heuristics",
    ),
]


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
            # Validate word distribution before accepting result
            if not _validate_section_distribution(result.sections, pdf_path):
                log.warning(
                    f"  Layer {layer.name}: Suspicious word distribution - "
                    f"falling back to next layer"
                )
                continue  # Try next detection layer

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


# =============================================================================
# PDF Parser Class
# =============================================================================


class PdfParser(BookParser):
    """Parse PDF files and extract structure using cascade detection."""

    def __init__(self, pdf_path: Path, pages_per_chunk: int | None = None):
        self.path = pdf_path
        self._detection_result: DetectionResult | None = None
        self._pages_per_chunk = pages_per_chunk

        try:
            self._reader = pypdf.PdfReader(str(pdf_path))
        except FileNotDecryptedError:
            raise ValueError("PDF is encrypted. Please decrypt first.")
        except EmptyFileError:
            raise ValueError("PDF file is empty.")
        except PdfReadError as e:
            raise ValueError(f"PDF appears corrupted: {e}")

    def parse(self) -> ParsedBook:
        """Parse the PDF and return complete structure."""
        # Check for empty PDF
        if len(self._reader.pages) == 0:
            raise ValueError("PDF has no pages.")

        # Check for scanned PDF (limited text extraction)
        sample_text = self._extract_sample_text()
        warnings_list: list[str] = []

        if self._pages_per_chunk is not None:
            log.info(f"Forced page-based chunking (--by-page {self._pages_per_chunk})")
            self._detection_result = chunk_by_pages(self.path, self._pages_per_chunk)
        elif len(sample_text.strip()) < 100:
            log.warning(
                "PDF appears to have limited text content. "
                "May be scanned or image-based."
            )
            warnings_list.append(
                "Limited text detected. PDF may be scanned/image-based. "
                "Using page-based chunking."
            )
            # Use page chunking fallback for scanned PDFs
            self._detection_result = chunk_by_pages(self.path)
        else:
            # Run cascade detection
            self._detection_result = detect_sections(self.path)

        # Add low confidence warning if applicable
        if self._detection_result.confidence < 0.5:
            warnings_list.append(
                f"Low extraction confidence ({self._detection_result.confidence:.2f}). "
                "Section boundaries may be inaccurate."
            )

        # Combine warnings
        all_warnings = warnings_list + self._detection_result.warnings

        # Extract content for each detected section
        chapters = self._extract_chapters()

        return ParsedBook(
            metadata=self.get_metadata(),
            toc=self._build_toc(),
            chapters=chapters,
            spine_order=[],  # N/A for PDF
            source_format="pdf",
            extraction_method=self._detection_result.method,
            extraction_confidence=self._detection_result.confidence,
            warnings=all_warnings,
        )

    def get_metadata(self) -> BookMetadata:
        """Extract book metadata from PDF."""
        info = self._reader.metadata or {}

        # Extract title (try multiple fields)
        title = None
        if info.get("/Title"):
            title = str(info.get("/Title"))
        if not title:
            title = self.path.stem

        # Extract author
        authors = []
        if info.get("/Author"):
            author_str = str(info.get("/Author"))
            # Split on common separators
            if "," in author_str:
                authors = [a.strip() for a in author_str.split(",")]
            elif ";" in author_str:
                authors = [a.strip() for a in author_str.split(";")]
            else:
                authors = [author_str]

        return BookMetadata(
            title=title,
            authors=authors,
            language=None,  # Not standard in PDF metadata
            publisher=str(info.get("/Producer", "")) or None,
            publication_date=str(info.get("/CreationDate", "")) or None,
        )

    def _extract_sample_text(self) -> str:
        """Extract sample text to detect scanned PDFs."""
        sample_pages = min(5, len(self._reader.pages))
        text_parts = []
        for i in range(sample_pages):
            text_parts.append(self._reader.pages[i].extract_text() or "")
        return " ".join(text_parts)

    def _build_toc(self) -> list[TOCEntry]:
        """Build TOC from detected sections."""
        if not self._detection_result:
            return []

        entries = []
        for i, section in enumerate(self._detection_result.sections):
            entries.append(
                TOCEntry(
                    id=f"section_{i + 1:03d}",
                    title=section.title,
                    href=f"page_{section.page_start or 0}",
                    level=section.level,
                    children=[],
                )
            )
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

            chapters.append(
                Chapter(
                    id=f"chapter_{i + 1:03d}",
                    title=section.title,
                    index=i,
                    file_name=f"pages_{page_start + 1}-{page_end + 1}",
                    raw_content=content.encode("utf-8"),
                    word_count=len(content.split()),
                    has_images=False,  # TODO: Image detection
                    page_start=page_start,
                    page_end=page_end,
                    extraction_confidence=section.confidence,
                    extraction_method=self._detection_result.method,
                    level=section.level,
                )
            )

        return chapters

    def _extract_page_range(self, start: int, end: int) -> str:
        """Extract text from a range of pages."""
        text_parts = []
        for page_num in range(start, end + 1):
            if page_num < len(self._reader.pages):
                page = self._reader.pages[page_num]
                text_parts.append(page.extract_text() or "")
        return "\n\n".join(text_parts)
