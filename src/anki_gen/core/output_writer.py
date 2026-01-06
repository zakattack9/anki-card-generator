"""Write parsed chapters to output directory."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from anki_gen.core.content_processor import ContentProcessor
from anki_gen.models.epub import Chapter, ParsedEpub
from anki_gen.models.output import BookOutput, ChapterMetadata, ChapterOutput


class OutputWriter:
    """Write parsed chapters to output directory."""

    def __init__(self, output_dir: Path, source_epub: Path):
        self.output_dir = output_dir
        self.source_epub = source_epub
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.processor = ContentProcessor()

    def write_chapter(
        self,
        chapter: Chapter,
        output_format: Literal["markdown", "text", "html"] = "markdown",
    ) -> tuple[Path, ChapterMetadata]:
        """Write single chapter to JSON file."""
        # Process content
        content = self.processor.process(chapter.raw_content, output_format)
        stats = self.processor.get_stats(content)

        # Create metadata
        metadata = ChapterMetadata(
            chapter_id=chapter.id,
            chapter_index=chapter.index,
            title=chapter.title,
            source_file=chapter.file_name,
            source_epub=str(self.source_epub),
            extracted_at=datetime.now(),
            word_count=stats["word_count"],
            character_count=stats["character_count"],
            paragraph_count=stats["paragraph_count"],
        )

        # Create output
        output = ChapterOutput(
            metadata=metadata,
            content=content,
            format=output_format,
        )

        # Write file
        filename = f"chapter_{chapter.index + 1:03d}.json"
        filepath = self.output_dir / filename
        filepath.write_text(output.model_dump_json(indent=2))

        return filepath, metadata

    def write_manifest(
        self,
        parsed_epub: ParsedEpub,
        extracted_indices: list[int],
        chapter_metadata: list[ChapterMetadata],
    ) -> Path:
        """Write book manifest file."""
        manifest = BookOutput(
            book_title=parsed_epub.metadata.title,
            authors=parsed_epub.metadata.authors,
            total_chapters=len(parsed_epub.chapters),
            extracted_chapters=extracted_indices,
            output_directory=str(self.output_dir),
            created_at=datetime.now(),
            chapters=chapter_metadata,
        )

        filepath = self.output_dir / "manifest.json"
        filepath.write_text(manifest.model_dump_json(indent=2))
        return filepath
