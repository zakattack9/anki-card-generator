"""Cache management with hash/mtime invalidation."""

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

from anki_gen.cache.models import (
    CachedChapter,
    CachedEpubStructure,
    CacheIndex,
    CacheMetadata,
)
from anki_gen.models.epub import ParsedEpub


class CacheManager:
    """Manages caching of parsed EPUB structures."""

    CACHE_DIR = ".anki_gen_cache"
    INDEX_FILE = "index.json"
    CACHE_VERSION = "1.0"

    def __init__(self, project_dir: Path):
        self.cache_root = project_dir / self.CACHE_DIR
        self.index_path = self.cache_root / self.INDEX_FILE
        self._index: CacheIndex | None = None

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist."""
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> CacheIndex:
        """Load or create cache index."""
        if self._index is not None:
            return self._index

        if self.index_path.exists():
            try:
                data = json.loads(self.index_path.read_text())
                self._index = CacheIndex.model_validate(data)
            except Exception:
                self._index = CacheIndex()
        else:
            self._index = CacheIndex()

        return self._index

    def _save_index(self) -> None:
        """Save cache index to disk."""
        self._ensure_cache_dir()
        index = self._load_index()
        self.index_path.write_text(index.model_dump_json(indent=2))

    def get_file_hash(self, epub_path: Path) -> str:
        """Compute SHA-256 hash of EPUB file."""
        sha256 = hashlib.sha256()
        with open(epub_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def is_cache_valid(self, epub_path: Path) -> bool:
        """Check if cached data exists and is still valid."""
        if not self.cache_root.exists():
            return False

        index = self._load_index()
        path_key = str(epub_path.resolve())

        if path_key not in index.entries:
            return False

        file_hash = index.entries[path_key]
        cache_file = self.cache_root / "books" / file_hash / "structure.json"

        if not cache_file.exists():
            return False

        # Load cached metadata
        try:
            cached = CachedEpubStructure.model_validate_json(cache_file.read_text())
        except Exception:
            return False

        stat = epub_path.stat()

        # Fast path: check mtime and size first
        if (
            cached.cache_metadata.file_mtime == stat.st_mtime
            and cached.cache_metadata.file_size == stat.st_size
        ):
            return True

        # Slow path: mtime changed, verify with hash
        current_hash = self.get_file_hash(epub_path)
        if cached.cache_metadata.file_hash == current_hash:
            # File unchanged, update mtime in cache
            cached.cache_metadata.file_mtime = stat.st_mtime
            cache_file.write_text(cached.model_dump_json(indent=2))
            return True

        return False

    def get_cached_structure(self, epub_path: Path) -> CachedEpubStructure | None:
        """Retrieve cached EPUB structure if valid."""
        if not self.is_cache_valid(epub_path):
            return None

        index = self._load_index()
        path_key = str(epub_path.resolve())
        file_hash = index.entries[path_key]
        cache_file = self.cache_root / "books" / file_hash / "structure.json"

        try:
            return CachedEpubStructure.model_validate_json(cache_file.read_text())
        except Exception:
            return None

    def save_structure(self, epub_path: Path, parsed: ParsedEpub) -> None:
        """Save parsed EPUB structure to cache."""
        stat = epub_path.stat()
        file_hash = self.get_file_hash(epub_path)

        cache_metadata = CacheMetadata(
            epub_path=str(epub_path.resolve()),
            file_hash=file_hash,
            file_size=stat.st_size,
            file_mtime=stat.st_mtime,
            cached_at=datetime.now(),
            cache_version=self.CACHE_VERSION,
        )

        cached_chapters = [
            CachedChapter(
                id=ch.id,
                title=ch.title,
                index=ch.index,
                file_name=ch.file_name,
                word_count=ch.word_count,
                has_images=ch.has_images,
            )
            for ch in parsed.chapters
        ]

        structure = CachedEpubStructure(
            cache_metadata=cache_metadata,
            book_metadata=parsed.metadata,
            toc=parsed.toc,
            chapters=cached_chapters,
            spine_order=parsed.spine_order,
        )

        # Save to cache
        cache_dir = self.cache_root / "books" / file_hash
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "structure.json"
        cache_file.write_text(structure.model_dump_json(indent=2))

        # Update index
        index = self._load_index()
        index.entries[str(epub_path.resolve())] = file_hash
        self._save_index()

    def clear_cache(self) -> int:
        """Clear all cached data. Returns number of entries cleared."""
        if not self.cache_root.exists():
            return 0

        books_dir = self.cache_root / "books"
        if books_dir.exists():
            count = len(list(books_dir.iterdir()))
        else:
            count = 0

        shutil.rmtree(self.cache_root)
        self._index = None
        return count

    def list_cached(self) -> list[tuple[str, str]]:
        """List all cached EPUBs. Returns list of (path, hash)."""
        index = self._load_index()
        return list(index.entries.items())
