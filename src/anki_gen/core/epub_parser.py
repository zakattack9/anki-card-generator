"""EPUB parsing using ebooklib."""

import warnings
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from ebooklib import epub

from anki_gen.models.epub import BookMetadata, Chapter, ParsedEpub, TOCEntry

# Suppress XML parsing warnings - EPUB files often use XHTML
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


class EpubParser:
    """Parse EPUB files and extract structure."""

    def __init__(self, epub_path: Path):
        self.path = epub_path
        self.book = epub.read_epub(str(epub_path))

    def parse(self) -> ParsedEpub:
        """Parse the EPUB and return complete structure."""
        return ParsedEpub(
            metadata=self._get_metadata(),
            toc=self._get_toc(),
            chapters=self._get_chapters(),
            spine_order=self._get_spine(),
        )

    def _get_metadata(self) -> BookMetadata:
        """Extract book metadata."""
        title = self.book.get_metadata("DC", "title")
        authors = self.book.get_metadata("DC", "creator")
        language = self.book.get_metadata("DC", "language")
        publisher = self.book.get_metadata("DC", "publisher")

        return BookMetadata(
            title=title[0][0] if title else "Unknown Title",
            authors=[a[0] for a in authors] if authors else [],
            language=language[0][0] if language else None,
            publisher=publisher[0][0] if publisher else None,
        )

    def _get_toc(self) -> list[TOCEntry]:
        """Extract hierarchical table of contents."""
        return self._parse_toc_recursive(self.book.toc)

    def _parse_toc_recursive(
        self, toc_items: list, level: int = 0
    ) -> list[TOCEntry]:
        """Recursively parse TOC structure."""
        entries = []

        for item in toc_items:
            if isinstance(item, tuple):
                # Section with children: (Section, [children])
                section, children = item
                entry = TOCEntry(
                    id=section.href.split("#")[0] if section.href else "",
                    title=section.title or "Untitled",
                    href=section.href or "",
                    level=level,
                    children=self._parse_toc_recursive(children, level + 1),
                )
            else:
                # Simple link
                entry = TOCEntry(
                    id=item.href.split("#")[0] if item.href else "",
                    title=item.title or "Untitled",
                    href=item.href or "",
                    level=level,
                )
            entries.append(entry)

        return entries

    def _get_spine(self) -> list[str]:
        """Get reading order from spine."""
        return [item[0] for item in self.book.spine]

    def _get_chapters(self) -> list[Chapter]:
        """Extract all document items as chapters."""
        # Build a map of file names to TOC titles
        toc_titles = self._build_toc_title_map()

        chapters = []
        index = 0

        for item in self.book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            content = item.get_content()
            file_name = item.get_name()

            # Try TOC title first, then extract from content, then use file name
            title = (
                toc_titles.get(file_name)
                or self._extract_title_from_content(content)
                or file_name
            )
            word_count = self._count_words(content)

            chapters.append(
                Chapter(
                    id=item.get_id(),
                    title=title,
                    index=index,
                    file_name=file_name,
                    raw_content=content,
                    word_count=word_count,
                    has_images=b"<img" in content.lower(),
                )
            )
            index += 1

        return chapters

    def _build_toc_title_map(self) -> dict[str, str]:
        """Build a map of file names to TOC titles."""
        title_map: dict[str, str] = {}
        self._collect_toc_titles(self.book.toc, title_map)
        return title_map

    def _collect_toc_titles(
        self, toc_items: list, title_map: dict[str, str]
    ) -> None:
        """Recursively collect titles from TOC."""
        for item in toc_items:
            if isinstance(item, tuple):
                section, children = item
                if section.href and section.title:
                    # Extract file name (remove fragment)
                    file_ref = section.href.split("#")[0]
                    if file_ref not in title_map:
                        title_map[file_ref] = section.title
                self._collect_toc_titles(children, title_map)
            else:
                if item.href and item.title:
                    file_ref = item.href.split("#")[0]
                    if file_ref not in title_map:
                        title_map[file_ref] = item.title

    def _extract_title_from_content(self, content: bytes) -> str | None:
        """Try to extract title from HTML content."""
        try:
            soup = BeautifulSoup(content, "lxml")
            # Try h1 first, then h2, then title tag
            for tag in ["h1", "h2", "title"]:
                element = soup.find(tag)
                if element:
                    text = element.get_text(strip=True)
                    if text:
                        return text
        except Exception:
            pass
        return None

    def _count_words(self, content: bytes) -> int:
        """Count words in HTML content."""
        try:
            soup = BeautifulSoup(content, "lxml")
            text = soup.get_text(separator=" ", strip=True)
            return len(text.split())
        except Exception:
            return 0
