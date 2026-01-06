# anki-gen

A CLI tool for parsing EPUB files and generating Anki flashcards using AI.

## Overview

`anki-gen` extracts chapters from EPUB books and generates AI-powered Anki flashcards using the Gemini CLI. The tool:
1. Parses EPUB files into structured JSON with Markdown content
2. Generates both basic (Q&A) and cloze deletion flashcards
3. Outputs Anki-importable text files

## Installation

```bash
# Clone or navigate to the project directory
cd anki_gen

# Install in editable mode
pip install -e .
```

## Usage

### View Book Information

Display metadata and table of contents for an EPUB file:

```bash
anki-gen info book.epub
```

Output:
```
╭─────────────────── Book Information ───────────────────╮
│ The Everything American Government Book                │
│                                                        │
│ Author(s): Nick Ragone                                 │
│ Language: en                                           │
│ Publisher: F+W Media, Inc.                             │
│ Total Chapters: 35                                     │
╰────────────────────────────────────────────────────────╯

                Table of Contents
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ #  ┃ Title                        ┃ Words ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ 1  │ Title Page                   │    23 │
│ 2  │ Introduction                 │   547 │
│ 3  │ 1: The Birth of a Nation     │ 3,388 │
│ 4  │ 2: The Constitution          │ 2,755 │
│ ...│ ...                          │   ... │
└────┴──────────────────────────────┴───────┘
```

### Parse Chapters

#### Interactive Mode (Default)

When no `--chapters` flag is provided, the tool displays the table of contents and prompts for selection:

```bash
anki-gen parse book.epub
```

You'll see the TOC and can enter:
- Specific chapters: `1,3,5`
- Ranges: `1-5`
- Mixed: `1,3,5-10`
- All chapters: `all`

#### Direct Chapter Selection

Extract specific chapters without interactive prompts:

```bash
# Single chapters
anki-gen parse book.epub --chapters 1,3,5

# Chapter range
anki-gen parse book.epub --chapters 1-10

# Mixed selection
anki-gen parse book.epub --chapters 1,3,5-10,15

# All chapters
anki-gen parse book.epub --chapters all
```

#### Additional Options

```bash
# Specify output directory
anki-gen parse book.epub --chapters 1-5 --output-dir ./my_output

# Choose output format (markdown, text, or html)
anki-gen parse book.epub --chapters 1-5 --format text

# Force re-parse (ignore cache)
anki-gen parse book.epub --chapters 1-5 --force

# Quiet mode (suppress progress output)
anki-gen parse book.epub --chapters 1-5 --quiet
```

### Cache Management

The tool caches parsed EPUB structures to speed up repeated operations.

```bash
# List cached EPUBs
anki-gen cache list

# Clear all cached data
anki-gen cache clear
```

### Generate Flashcards

Generate AI-powered flashcards from parsed chapters using the Gemini CLI:

```bash
# Generate flashcards (AI decides card count)
anki-gen generate ./book_chapters/

# Limit cards per chapter
anki-gen generate ./book_chapters/ --max-cards 20

# Use a different Gemini model
anki-gen generate ./book_chapters/ --model gemini-2.5-pro

# Preview what would be processed (no API calls)
anki-gen generate ./book_chapters/ --dry-run
```

**Requirements:**
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) must be installed and authenticated

**Output Files:**
For each chapter, generates:
- `chapter_XXX_basic.txt` - Basic Q&A flashcards (pipe-separated)
- `chapter_XXX_cloze.txt` - Cloze deletion flashcards (pipe-separated)
- `chapter_XXX_meta.json` - Generation metadata

## Output Format

Extracted chapters are saved in a folder next to the EPUB file (e.g., `bookname_chapters/`).

### Directory Structure

```
bookname_chapters/
├── manifest.json           # Book metadata and extraction info
├── chapter_001.json        # First extracted chapter
├── chapter_001_basic.txt   # Basic flashcards (after generate)
├── chapter_001_cloze.txt   # Cloze flashcards (after generate)
├── chapter_001_meta.json   # Generation metadata (after generate)
├── chapter_002.json        # Second extracted chapter
└── ...
```

### Chapter JSON Format

Each chapter file contains metadata and Markdown content optimized for AI processing:

```json
{
  "metadata": {
    "chapter_id": "ch001",
    "chapter_index": 0,
    "title": "1: The Birth of a Nation",
    "source_file": "text/part0009.html",
    "source_epub": "/path/to/book.epub",
    "extracted_at": "2025-01-05T10:30:00Z",
    "word_count": 3388,
    "character_count": 22331,
    "paragraph_count": 87
  },
  "content": "# The Birth of a Nation\n\nThe American government is an institution...",
  "format": "markdown",
  "ai_processing": null
}
```

### Manifest JSON Format

The manifest provides an overview of the extraction:

```json
{
  "book_title": "The Everything American Government Book",
  "authors": ["Nick Ragone"],
  "total_chapters": 35,
  "extracted_chapters": [0, 1, 2],
  "output_directory": "/path/to/bookname_chapters",
  "created_at": "2025-01-05T10:30:00Z",
  "chapters": [
    {
      "chapter_id": "ch001",
      "chapter_index": 0,
      "title": "1: The Birth of a Nation",
      "word_count": 3388
    }
  ]
}
```

### Flashcard Format

Generated flashcards use pipe-separated format, directly importable into Anki:

**Basic Cards** (`chapter_XXX_basic.txt`):
```
What document established the framework for American government?|The Constitution of the United States, ratified in 1788
What year was the Constitution ratified?|1788
```

**Cloze Cards** (`chapter_XXX_cloze.txt`):
```
The {{c1::Constitution}} was ratified in {{c2::1788}}.|Fundamental U.S. governing document
The {{c1::Bill of Rights}} consists of the first {{c2::ten}} amendments.|Ratified in 1791
```

**Import into Anki:**
1. Open Anki → File → Import
2. Select the `.txt` file
3. Set field separator to `Pipe`
4. For cloze cards, select "Cloze" as the note type

## Workflow Example

A typical workflow for creating Anki flashcards:

```bash
# 1. Check what's in the book
anki-gen info "American Government.epub"

# 2. Extract chapters 1-3 for studying
anki-gen parse "American Government.epub" --chapters 1-3

# 3. Generate flashcards from the extracted chapters
anki-gen generate American_Government_chapters/

# 4. Import the generated .txt files into Anki
#    - chapter_001_basic.txt
#    - chapter_001_cloze.txt
#    - etc.

# 5. Later, come back and process more chapters
anki-gen parse "American Government.epub" --chapters 4-6
anki-gen generate American_Government_chapters/
```

## Caching

The tool automatically caches parsed EPUB structures in `.anki_gen_cache/` to speed up repeated operations:

- Cache is stored in the same directory as the EPUB file
- Cache invalidation uses file hash and modification time
- Use `--force` to bypass cache and re-parse
- Use `anki-gen cache clear` to remove all cached data

## Roadmap

Completed:
- [x] `anki-gen parse` - Extract chapters from EPUB files
- [x] `anki-gen generate` - AI-powered flashcard generation using Gemini CLI
- [x] Basic and cloze card generation
- [x] Anki-importable output format

Future features planned:
- [ ] `anki-gen export` - Combine multiple chapter flashcards into single file
- [ ] Support for multiple AI providers (OpenAI, Anthropic, Claude)
- [ ] Customizable flashcard templates
- [ ] Batch processing of multiple EPUBs

## Requirements

- Python 3.10+
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) (for `generate` command)
- Dependencies (installed automatically):
  - typer
  - ebooklib
  - beautifulsoup4
  - lxml
  - pydantic
  - rich
  - markdownify
