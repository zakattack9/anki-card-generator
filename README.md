# anki-gen

A CLI tool for parsing EPUB files and generating Anki flashcards using AI.

## Overview

`anki-gen` extracts sections from EPUB books and generates AI-powered Anki flashcards using the Gemini CLI. The tool:
1. Parses EPUB files into structured JSON with Markdown content
2. Generates both basic (Q&A) and cloze deletion flashcards
3. Outputs Anki-importable text files

**Note:** EPUB "sections" include all spine items (title pages, TOC, chapters, appendices). Use `anki-gen info` to see the index numbers and select the sections you want.

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

### Parse Sections

#### Interactive Mode (Default)

When no `--sections` flag is provided, the tool displays the table of contents and prompts for selection:

```bash
anki-gen parse book.epub
```

You'll see the TOC and can enter:
- Specific sections: `1,3,5`
- Ranges: `1-5`
- Mixed: `1,3,5-10`
- All sections: `all`

#### Direct Section Selection

Extract specific sections without interactive prompts:

```bash
# Single sections
anki-gen parse book.epub --sections 1,3,5

# Section range
anki-gen parse book.epub --sections 1-10

# Mixed selection
anki-gen parse book.epub --sections 1,3,5-10,15

# All sections
anki-gen parse book.epub --sections all
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

### Check Status

View a summary of what has been parsed, generated, and exported for a book:

```bash
anki-gen status ./book_chapters/
```

Output:
```
╭─────────────────── Book Information ───────────────────╮
│ The Everything American Government Book                │
│                                                        │
│ Author(s): Nick Ragone                                 │
│ Output directory: ./book_chapters                      │
│ Created: 2025-01-05 10:30                              │
│                                                        │
│ EPUB total sections: 35                                │
│ Status: Generated                                      │
╰────────────────────────────────────────────────────────╯

╭─────────────────── Progress Summary ───────────────────╮
│ Sections parsed: 3 of 35                               │
│ Sections generated: 3 of 3                             │
│ Total cards: 135 (85 basic, 50 cloze)                  │
│ Exported: No                                           │
╰────────────────────────────────────────────────────────╯

                    Section Details
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━┓
┃ #  ┃ Title                      ┃ Words ┃ Parsed ┃ Generated ┃ Basic ┃ Cloze ┃ Total ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━┩
│ 10 │ 1- The Birth of a Nation   │ 3,388 │   ✓    │     ✓     │    28 │    17 │    45 │
│ 11 │ 2- The Constitution        │ 2,755 │   ✓    │     ✓     │    32 │    18 │    50 │
│ 12 │ 3- The Bill of Rights      │ 2,100 │   ✓    │     ✓     │    25 │    15 │    40 │
├────┼────────────────────────────┼───────┼────────┼───────────┼───────┼───────┼───────┤
│    │ Total                      │       │      3 │         3 │    85 │    50 │   135 │
└────┴────────────────────────────┴───────┴────────┴───────────┴───────┴───────┴───────┘

Next step: Run anki-gen export ./book_chapters/ to create combined import file
```

The status command shows:
- Book metadata and output location
- Overall progress (parsed → generated → exported)
- Per-section breakdown with card counts
- Suggested next step based on current state

### Cache Management

The tool caches parsed EPUB structures to speed up repeated operations.

```bash
# List cached EPUBs
anki-gen cache list

# Clear all cached data
anki-gen cache clear
```

### Generate Flashcards

Generate AI-powered flashcards from parsed sections using the Gemini CLI:

```bash
# Generate flashcards for all sections
anki-gen generate ./book_chapters/

# Generate for specific sections only
anki-gen generate ./book_chapters/ --sections 10,11,12

# Generate for a range of sections
anki-gen generate ./book_chapters/ --sections 10-15

# Limit total cards per section
anki-gen generate ./book_chapters/ --max-cards 30

# Override the auto-generated deck name
anki-gen generate ./book_chapters/ --deck "My Custom Deck"

# Add extra global tags
anki-gen generate ./book_chapters/ --tag study --tag exam-prep

# Use a different Gemini model
anki-gen generate ./book_chapters/ --model gemini-2.5-pro

# Preview what would be processed (no API calls)
anki-gen generate ./book_chapters/ --dry-run
```

**Requirements:**
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) must be installed and authenticated

**Output Files:**
For each section, generates a single combined file:
- `chapter_XXX_cards.txt` - Combined Basic + Cloze flashcards with Anki headers
- `chapter_XXX_meta.json` - Generation metadata

**Features:**
- Single API call per section (unified prompt generates both card types)
- AI decides optimal card type (Basic vs Cloze) for each fact
- No duplicate facts between card types
- Automatic deck hierarchy: `Book Title::Section Title`
- Per-card topic tags generated by AI
- GUID support for re-importing/updating cards

## Output Format

Extracted chapters are saved in a folder next to the EPUB file (e.g., `bookname_chapters/`).

### Directory Structure

```
bookname_chapters/
├── manifest.json           # Book metadata and extraction info
├── chapter_001.json        # First extracted chapter
├── chapter_001_cards.txt   # Combined flashcards (after generate)
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

Generated flashcards use a combined format with Anki file headers (requires Anki 2.1.54+):

**Combined Cards** (`chapter_XXX_cards.txt`):
```
#separator:Pipe
#html:true
#deck:The Everything American Government Book::2- The Constitution
#tags:anki-gen the-everything-american-government-book
#notetype column:1
#tags column:4
#guid column:5
#columns:Note Type|Field 1|Field 2|Tags|GUID
Basic|What are the three branches of government?|Legislative, Executive, and Judicial|branches constitution|the-everything-american-government-book-ch011-001
Cloze|The Constitution was ratified in {{c1::1788}}.|Replaced the Articles of Confederation|constitution dates|the-everything-american-government-book-ch011-002
Basic|Why did framers create checks and balances?|To prevent any single branch from dominating|checks-balances framers-intent|the-everything-american-government-book-ch011-003
Cloze|The House has {{c1::435}} members.|Set by 1929 Reapportionment Act|house congress|the-everything-american-government-book-ch011-004
```

**Import into Anki:**
1. Open Anki → File → Import
2. Select the `_cards.txt` file
3. Anki will auto-detect settings from file headers
4. Cards are automatically placed in the correct deck with tags

### Export Combined Cards

Combine all section card files into a single Anki-importable file:

```bash
# Export all sections to single file
anki-gen export ./book_chapters/

# Specify custom output path
anki-gen export ./book_chapters/ --output flashcards.txt

# Quiet mode (suppress stats)
anki-gen export ./book_chapters/ --quiet
```

**Output:**
- Creates `all_cards.txt` (or custom filename) with all cards combined
- Preserves per-section deck hierarchy (`Book::Section Title`, etc.)
- Single import into Anki instead of multiple files
- Displays statistics summary showing cards per section

**Example Stats Output:**
```
╭──────────────────── Export Complete ────────────────────╮
│ Exported 450 cards from 10 section(s)                   │
│                                                         │
│ Basic cards: 280                                        │
│ Cloze cards: 170                                        │
│ Output file: ./book_chapters/all_cards.txt              │
╰─────────────────────────────────────────────────────────╯

           Per-Section Breakdown
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━┓
┃ #  ┃ Section                  ┃ Basic ┃ Cloze ┃ Total ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━┩
│ 10 │ 1- The Birth of a Nat... │    28 │    17 │    45 │
│ 11 │ 2- The Constitution      │    32 │    18 │    50 │
│ ...│ ...                      │   ... │   ... │   ... │
├────┼──────────────────────────┼───────┼───────┼───────┤
│    │ Total                    │   280 │   170 │   450 │
└────┴──────────────────────────┴───────┴───────┴───────┘
```

## Workflow Example

A typical workflow for creating Anki flashcards:

```bash
# 1. Check what's in the book (note the section indices)
anki-gen info "American Government.epub"

# 2. Extract sections 10-12 (the actual chapter content, not front matter)
anki-gen parse "American Government.epub" --sections 10-12

# 3. Generate flashcards from the extracted sections
anki-gen generate American_Government_chapters/

# 4. Check progress at any time
anki-gen status American_Government_chapters/

# 5. Export all cards to a single file
anki-gen export American_Government_chapters/

# 6. Import all_cards.txt into Anki
#    - Single file contains all sections
#    - Each card goes to its section deck automatically
#    - Anki auto-detects deck, tags, and note types from headers

# 7. Later, come back and process more sections
anki-gen parse "American Government.epub" --sections 13-15
anki-gen generate American_Government_chapters/ --sections 13-15
anki-gen export American_Government_chapters/  # Re-export with new sections
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
- [x] `anki-gen export` - Combine multiple chapter flashcards into single file
- [x] `anki-gen status` - Show progress summary of parsed/generated/exported sections
- [x] Unified prompt (single API call generates both Basic and Cloze cards)
- [x] AI-optimized card type selection (no duplicate facts)
- [x] Anki file headers (auto deck, tags, GUID support)
- [x] Per-card topic tags
- [x] Streaming output display

Future features planned:
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
