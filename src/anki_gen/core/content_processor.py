"""Process HTML content into AI-friendly formats."""

from typing import Literal

from bs4 import BeautifulSoup
from markdownify import markdownify as md


class ContentProcessor:
    """Process HTML content into AI-friendly formats."""

    def process(
        self,
        html_content: bytes,
        output_format: Literal["markdown", "text", "html"] = "markdown",
    ) -> str:
        """Convert HTML to specified format."""
        soup = BeautifulSoup(html_content, "lxml")

        # Remove scripts, styles, and navigation elements
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        if output_format == "html":
            return self._to_clean_html(soup)
        elif output_format == "text":
            return self._to_plain_text(soup)
        else:  # markdown
            return self._to_markdown(soup)

    def _to_markdown(self, soup: BeautifulSoup) -> str:
        """Convert BeautifulSoup to clean Markdown."""
        body = soup.body or soup
        markdown = md(
            str(body),
            heading_style="ATX",
            bullets="-",
            strip=["a"],  # Remove link formatting but keep text
        )
        # Clean up excessive whitespace
        lines = [line.rstrip() for line in markdown.split("\n")]
        # Remove multiple consecutive blank lines
        cleaned = []
        prev_blank = False
        for line in lines:
            is_blank = not line.strip()
            if is_blank and prev_blank:
                continue
            cleaned.append(line)
            prev_blank = is_blank

        return "\n".join(cleaned).strip()

    def _to_plain_text(self, soup: BeautifulSoup) -> str:
        """Extract plain text with paragraph preservation."""
        paragraphs = []
        for p in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li"]):
            text = p.get_text(strip=True)
            if text:
                paragraphs.append(text)
        return "\n\n".join(paragraphs)

    def _to_clean_html(self, soup: BeautifulSoup) -> str:
        """Return cleaned HTML."""
        body = soup.body or soup
        return str(body)

    def get_stats(self, content: str) -> dict[str, int]:
        """Calculate content statistics."""
        words = content.split()
        paragraphs = [p for p in content.split("\n\n") if p.strip()]
        return {
            "word_count": len(words),
            "character_count": len(content),
            "paragraph_count": len(paragraphs),
        }
