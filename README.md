<p align="center">
  <img src="assets/anki-icon.png" alt="anki-gen icon" width="120" height="120">
</p>

<h1 align="center">anki-gen</h1>

<p align="center">
  <strong>A CLI tool for parsing EPUB files and generating Anki flashcards using AI.</strong>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#installation">Installation</a> •
  <a href="#commands">Commands</a> •
  <a href="#workflow-overview">Workflow</a>
</p>

---

## Quick Start

```bash
# Install
pip install -e .

# 1. See what's in your book
anki-gen info "My Book.epub"

# 2. Parse the sections you want (e.g., sections 10-15)
anki-gen parse "My Book.epub" --sections 10-15

# 3. Generate flashcards
anki-gen generate ./My_Book_chapters/

# 4. Export to single file and import into Anki
anki-gen export ./My_Book_chapters/
# → Import all_cards.txt into Anki (File → Import)
```

## Installation

**Requirements:**
- Python 3.10+
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) (for flashcard generation)

```bash
pip install -e .
```

## Workflow Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  EPUB File                                                      │
│    ↓                                                            │
│  anki-gen info    → See sections and word counts                │
│    ↓                                                            │
│  anki-gen parse   → Extract sections to JSON/Markdown           │
│    ↓                                                            │
│  anki-gen generate → AI creates Basic + Cloze flashcards        │
│    ↓                                                            │
│  anki-gen status  → Check progress anytime                      │
│    ↓                                                            │
│  anki-gen export  → Combine into single Anki import file        │
│    ↓                                                            │
│  Import into Anki → Cards auto-sorted into decks with tags      │
└─────────────────────────────────────────────────────────────────┘
```

**Note:** EPUB "sections" include all spine items (title pages, TOC, chapters, appendices). Use `anki-gen info` to see indices and pick the content sections you want.

## Commands

### `anki-gen info <epub>`

Display book metadata and table of contents with word counts.

```bash
anki-gen info "American Government.epub"
```

Output:
```
╭─────────────────── Book Information ───────────────────╮
│ The Everything American Government Book                │
│                                                        │
│ Author(s): Nick Ragone                                 │
│ Language: en                                           │
│ Publisher: F+W Media, Inc.                             │
│ Total Sections: 35                                     │
╰────────────────────────────────────────────────────────╯

                Table of Contents
┏━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ #    ┃ Title                        ┃ Words ┃
┡━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ 1    │ Title Page                   │    23 │
│ 2    │ Copyright                    │   156 │
│ ...  │ ...                          │   ... │
│ 10   │ 1: The Birth of a Nation     │ 3,388 │
│ 11   │ 2: The Constitution          │ 2,755 │
│ 12   │ 3: The Bill of Rights        │ 3,055 │
│ ...  │ ...                          │   ... │
└──────┴──────────────────────────────┴───────┘
```

### `anki-gen parse <epub>`

Extract sections from EPUB into structured JSON with Markdown content.

```bash
# Interactive mode - shows TOC, prompts for selection
anki-gen parse book.epub

# Direct selection
anki-gen parse book.epub --sections 10-15
anki-gen parse book.epub --sections 1,3,5-10,15
anki-gen parse book.epub --sections all

# Options
anki-gen parse book.epub --sections 10-15 \
  --output-dir ./custom_output \    # Custom output directory
  --format text \                   # Output format: markdown|text|html
  --force \                         # Ignore cache, re-parse
  --quiet \                         # Suppress progress output
  --interactive                     # Force interactive mode
```

Creates `{book_name}_chapters/` directory with:
- `manifest.json` - Book metadata
- `chapter_XXX.json` - Parsed section content

### `anki-gen generate <chapters_dir>`

Generate AI-powered flashcards using Gemini CLI.

```bash
# Generate for all parsed sections
anki-gen generate ./book_chapters/

# Generate specific sections
anki-gen generate ./book_chapters/ --sections 10-12

# Options
anki-gen generate ./book_chapters/ \
  --max-cards 30 \                  # Limit cards per section
  --deck "Custom Deck Name" \       # Override deck name
  --tag study --tag exam \          # Add global tags
  --model gemini-2.5-pro \          # Different Gemini model
  --dry-run \                       # Preview without API calls
  --quiet                           # Suppress progress output
```

Creates for each section:
- `chapter_XXX_cards.txt` - Flashcards with Anki headers
- `chapter_XXX_meta.json` - Generation metadata

**Features:**
- Single API call generates both Basic and Cloze cards
- AI picks optimal card type for each fact (no duplicates)
- Automatic deck hierarchy: `Book Title::Section Title`
- Per-card topic tags
- GUIDs for safe re-importing

### `anki-gen status <chapters_dir>`

Show progress summary of parsed, generated, and exported sections.

```bash
anki-gen status ./book_chapters/
```

Output:
```
╭────────────────────────── Book Information ──────────────────────────╮
│ The Everything American Government Book                              │
│                                                                      │
│ Author(s): Nick Ragone                                               │
│ EPUB total sections: 35                                              │
│ Status: Exported                                                     │
╰──────────────────────────────────────────────────────────────────────╯

╭────────────────────────── Progress Summary ──────────────────────────╮
│ Sections parsed: 3 of 35                                             │
│ Sections generated: 3 of 3                                           │
│ Total cards: 91 (30 basic, 61 cloze)                                 │
│ Exported: Yes (91 cards)                                             │
╰──────────────────────────────────────────────────────────────────────╯

                            Section Details
┏━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━┓
┃ #    ┃ Title                     ┃ Words ┃ Parsed ┃ Generated ┃ Basic ┃ Cloze ┃ Total ┃
┡━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━┩
│ 10   │ 1: The Birth of a Nation  │ 3,392 │   ✓    │     ✓     │    10 │    13 │    23 │
│ 11   │ 2: The Constitution       │ 2,760 │   ✓    │     ✓     │    15 │    24 │    39 │
│ 12   │ 3: The Bill of Rights     │ 3,055 │   ✓    │     ✓     │     5 │    24 │    29 │
├──────┼───────────────────────────┼───────┼────────┼───────────┼───────┼───────┼───────┤
│      │ Total                     │       │   3    │     3     │    30 │    61 │    91 │
└──────┴───────────────────────────┴───────┴────────┴───────────┴───────┴───────┴───────┘

Next step: Import ./book_chapters/all_cards.txt into Anki
```

### `anki-gen export <chapters_dir>`

Combine all section cards into a single Anki import file.

```bash
anki-gen export ./book_chapters/
anki-gen export ./book_chapters/ --output flashcards.txt
anki-gen export ./book_chapters/ --quiet
```

Creates `all_cards.txt` with:
- All cards from all sections
- Per-section deck hierarchy preserved
- Single import into Anki

### `anki-gen cache`

Manage cached EPUB parsing data.

```bash
anki-gen cache list    # Show cached EPUBs
anki-gen cache clear   # Remove all cache
```

Cache is stored in `.anki_gen_cache/` next to EPUB files. Use `--force` with parse to bypass.

## Output Format

### Flashcard Files

Generated cards use Anki's file header format (requires Anki 2.1.54+):

```
#separator:Pipe
#html:true
#deck:Book Title::Section Title
#notetype column:1
#tags column:4
#guid column:5
Basic|What are the three branches?|Legislative, Executive, Judicial|government|book-ch010-001
Cloze|The Constitution was ratified in {{c1::1788}}.|Replaced Articles of Confederation|constitution|book-ch010-002
```

**Importing:** File → Import in Anki. Settings auto-detected from headers. Requires Anki 2.1.54+.

### Directory Structure

```
book_chapters/
├── manifest.json           # Book metadata
├── chapter_010.json        # Parsed section
├── chapter_010_cards.txt   # Generated flashcards
├── chapter_010_meta.json   # Generation metadata
├── chapter_011.json
├── chapter_011_cards.txt
└── all_cards.txt           # Combined export
```

## Incremental Workflow

Process books over multiple sessions:

```bash
# Session 1: Parse and generate first few sections
anki-gen parse book.epub --sections 10-12
anki-gen generate ./book_chapters/
anki-gen export ./book_chapters/
# → Import all_cards.txt

# Session 2: Continue with more sections
anki-gen parse book.epub --sections 13-15
anki-gen generate ./book_chapters/ --sections 13-15
anki-gen export ./book_chapters/
# → Re-import all_cards.txt (GUIDs prevent duplicates)

# Check progress anytime
anki-gen status ./book_chapters/
```

## Roadmap

**Completed:**
- [x] `parse` - Extract sections from EPUB
- [x] `generate` - AI flashcard generation via Gemini
- [x] `export` - Combine cards into single file
- [x] `status` - Progress summary
- [x] Unified prompt (Basic + Cloze in one API call)
- [x] Per-card topic tags and GUIDs
- [x] Streaming output display

**Planned:**
- [ ] Multiple AI providers (OpenAI, Anthropic)
- [ ] Customizable flashcard templates
- [ ] Batch processing multiple EPUBs
- [ ] Image support in cards
