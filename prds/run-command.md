# PRD: Interactive `run` Command

## Overview

Add a new `anki-gen run` subcommand that provides an interactive, step-by-step wizard guiding users through the complete flashcard generation workflow (parse → generate → export) with intuitive configuration options.

## Goals

1. **Zero-friction onboarding** - New users can run `anki-gen run` with no arguments and be guided through everything
2. **Discoverability** - Users learn available options through the interactive UI rather than reading docs
3. **Smart defaults** - Sensible defaults at every step; users can accept all defaults or customize
4. **Resume support** - Detect previously generated sections and skip them by default

## User Flow

**Navigation:** Back navigation (`B` or `Esc`) available at every step, returning to the previous step in linear order:
```
Step 1 → Step 2 → Step 3 → Step 4 → Step 5
         ←Back    ←Back    ←Back
```

**Common Keyboard Shortcuts (all steps):**
| Key | Action |
|-----|--------|
| `↑`/`↓` | Navigate options |
| `Enter` | Confirm/Select |
| `B` or `Esc` | Go back |
| `Q` | Quit |

**Step-specific shortcuts are shown in each step's UI.**

### Step 1: File Selection

**Trigger:** `anki-gen run [BOOK_PATH]`

**If BOOK_PATH provided:**
- Validate file exists and is supported format (.pdf, .epub)
- Proceed to Step 2

**If BOOK_PATH omitted:**
- Scan current directory for `.pdf` and `.epub` files
- Display scrollable/selectable list:
  ```
  Select a book to process:

  > 1. Designing Data-Intensive Applications.pdf     (24.4 MB)
    2. The Everything American Government Book.epub  (1.2 MB)
    3. MBB2Neuro-1.pdf                               (1.5 MB)

  Use ↑↓ to navigate, Enter to select, q to quit
  ```
- If no supported files found, show error and exit

### Step 2: Book Preview & Section Selection

Display book metadata (similar to `info` command):

```
╭──────────────────────────── Book Info ────────────────────────────╮
│ Designing Data-Intensive Applications                             │
│ Author(s): Martin Kleppmann                                       │
│ Format: PDF                                                       │
│ Detection: PDF Outline (confidence: 95%)                          │
│ Total Sections: 47 (3 levels deep)                                │
╰───────────────────────────────────────────────────────────────────╯
```

**Depth Level Toggle:**

Allow user to cycle through depth levels to view/select sections at different granularities:

```
Section View: Level 1 of 3  [Press D to change depth]

┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┓
┃    ┃ Section                              ┃ Words  ┃ Status   ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━┩
│ [x]│ Part I: Foundations of Data Systems  │ 12,450 │ ✓ Done   │
│ [~]│ Part II: Distributed Data            │ 13,100 │ 1/3 done │
│ [ ]│ Part III: Derived Data               │ 10,600 │ Pending  │
└────┴──────────────────────────────────────┴────────┴──────────┘

[Space] Toggle  [A] Select All  [N] Select None  [D] Depth: 1→2  [Enter] Continue
```

(Note: Part II shows `[~]` because only some children are selected - see Level 2 view below)

**At Level 2:**
```
Section View: Level 2 of 3  [Press D to change depth]

┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┓
┃    ┃ Section                              ┃ Words  ┃ Status   ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━┩
│ [x]│ Part I: Foundations of Data Systems  │ 12,450 │ ✓ Done   │
│ [x]│   ├─ Chapter 1: Reliable Systems     │  3,200 │ ✓ Done   │
│ [x]│   ├─ Chapter 2: Data Models          │  4,100 │ ✓ Done   │
│ [x]│   └─ Chapter 3: Storage and Retrieval│  5,150 │ ✓ Done   │
│ [~]│ Part II: Distributed Data            │ 13,100 │ 1/3 done │
│ [x]│   ├─ Chapter 5: Replication          │  3,800 │ ✓ Done   │
│ [ ]│   ├─ Chapter 6: Partitioning         │  4,200 │ Pending  │
│ [ ]│   └─ Chapter 7: Transactions         │  5,100 │ Pending  │
│ [ ]│ Part III: Derived Data               │ 10,600 │ Pending  │
│ [ ]│   ├─ Chapter 10: Batch Processing    │  5,400 │ Pending  │
│ [ ]│   └─ Chapter 11: Stream Processing   │  5,200 │ Pending  │
└────┴──────────────────────────────────────┴────────┴──────────┘
```

(Note: Parent rows now show aggregated Word Count; Part II shows `[~]` and "1/3 done" since only Chapter 5 is selected)

**Initial State:**
- When entering Step 2 for the first time, **no sections are selected by default**
- User must explicitly select the sections they want to process
- Use `[A] Select All` for quick full-book selection

**Selection Behavior (Hybrid):**
- Selecting a parent at Level 1 auto-selects all its children
- At deeper levels, user can deselect specific children
- Deselecting all children auto-deselects the parent
- **Partial selection indicator:** Parent shows `[~]` when some (but not all) children are selected
- **Selections persist when changing depth levels** - switching from Level 2 → Level 1 preserves child selections

**Checkbox States:**
- `[x]` - Fully selected (all children selected if parent)
- `[ ]` - Not selected
- `[~]` - Partially selected (some children selected, some not)

**Depth Level vs Generation vs Deck Hierarchy:**

| Aspect | Behavior |
|--------|----------|
| **Viewing** | Depth level controls how sections are displayed (collapsed/expanded) |
| **Selection** | User selects at any level; children inherit parent selection |
| **Generation** | ALWAYS generates at the lowest subsection level for maximum quality |
| **Deck hierarchy** | Follows the selected depth level |

Example: User selects "Part I" at Level 1 (which contains Chapters 1-3)
- Generation: Creates cards for Chapter 1, Chapter 2, Chapter 3 individually
- Deck names: `Book::Part I` (not `Book::Part I::Chapter 1`)

Example: User selects at Level 2
- Generation: Same (individual chapters)
- Deck names: `Book::Part I::Chapter 1`, `Book::Part I::Chapter 2`, etc.

**Status Column:**
- `✓ Done` - Section fully generated (has `_cards.txt`)
- `Pending` - Not yet generated (including fresh books that have never been parsed)
- `3/5 done` - Parent with some children generated

**Word Count Column:**
- At deeper levels: Shows word count for that specific section
- At parent levels: Shows **sum of all child sections** (e.g., Part I shows 12,450 = Ch1 + Ch2 + Ch3)

**Empty Selection:**
- If user tries to continue with 0 sections selected, show message: "Please select at least one section"
- Block navigation to Step 3 until at least one section is selected

### Step 3: Generation Configuration

After section selection, show configuration screen:

```
╭─────────────────────── Generation Settings ───────────────────────╮
│                                                                   │
│  Output directory:    ./                         [Enter to edit]  │
│  Model:               gemini-3-pro-preview       [Enter to edit]  │
│  Deck name:           Auto (Book::Part::Ch)      [Enter to edit]  │
│  Max cards/section:   Unlimited                  [Enter to edit]  │
│  Tags:                (none)                     [Enter to edit]  │
│                                                                   │
│  ─────────────────────────────────────────────────────────────── │
│  [x] Skip already-generated sections (3 sections)                 │
│  [ ] Force regenerate all selected sections                       │
│                                                                   │
╰───────────────────────────────────────────────────────────────────╯

(Deck name preview reflects selected depth level - Level 2 in this example)

Use ↑↓ to navigate, Enter to edit, [C] Continue, [Q] Quit
```

**Field Behaviors:**

| Field | Default | Validation |
|-------|---------|------------|
| Output directory | Current directory (`./`) | Must exist; falls back to `./` if invalid |
| Model | `gemini-3-pro-preview` | Free text (no validation) |
| Deck name | `Auto (Book::Chapter)` | Free text or "Auto" (see below) |
| Max cards/section | `Unlimited` | Positive integer or "Unlimited" |
| Tags | `(none)` | Comma-separated list |

**Deck Name Behavior:**
- `Auto`: Deck hierarchy follows selected depth level (e.g., Level 2 = `Book::Part::Chapter`)
- Custom value (e.g., `MyDeck`): ALL cards go to single deck `MyDeck`, ignoring depth hierarchy
- Custom with `::`: User can create their own hierarchy (e.g., `Study::Biology::Chapter`)

**Regeneration Toggle:**
- Default: Skip already-generated sections
- User can toggle to force regenerate all
- Shows count of sections that will be skipped

**Export Format:**
- Fixed to `anki-txt` format for simplicity
- Users needing other formats (CSV, etc.) can use the `export` command directly after generation

### Step 4: Final Confirmation

Display summary before execution:

```
╭────────────────────────── Summary ──────────────────────────╮
│                                                             │
│  Book:        Designing Data-Intensive Applications         │
│  Format:      PDF (Outline detection)                       │
│                                                             │
│  Sections:    12 selected                                   │
│    • To generate: 8 sections (at lowest level)              │
│    • Skipping:    4 sections (already done)                 │
│                                                             │
│  Deck depth:  Level 2 (Book::Part::Chapter)                 │
│  Output:      ./all_cards.txt                               │
│  Model:       gemini-3-pro-preview                          │
│  Max cards:   Unlimited                                     │
│  Tags:        (none)                                        │
│                                                             │
╰─────────────────────────────────────────────────────────────╯

Estimated sections to process: 8
This will make API calls to Gemini for each section.

[Enter] Start  [B] Go Back  [Q] Quit
```

**Note:** The summary shows "Deck depth: Level 2" to clarify how deck names will be structured. Generation always happens at the lowest subsection level regardless of selected depth.

### Step 5: Execution

Run the full pipeline with progress display:

```
Processing: Designing Data-Intensive Applications

[1/3] Parsing PDF...
  ✓ Extracted 12 sections to ./Designing_Data_Intensive_Applications_chapters/

[2/3] Generating flashcards...
  [3/8] Chapter 6: Partitioning
  ████████████░░░░░░░░░░░░░░░░░░░░░░░░ 37%
  Generated: 12 basic, 8 cloze cards

[3/3] Exporting...
  ✓ Exported 245 cards to ./all_cards.txt

╭────────────────────────── Complete ──────────────────────────╮
│                                                              │
│  Total cards in export: 245 (142 basic, 103 cloze)          │
│    • Newly generated: 156 cards (8 sections)                 │
│    • Previously generated: 89 cards (4 sections)             │
│                                                              │
│  Import file: ./all_cards.txt                                │
│                                                              │
│  Next: Import into Anki via File → Import                    │
│                                                              │
╰──────────────────────────────────────────────────────────────╯
```

**Export Scope:**
- Export includes ALL SELECTED sections (both newly generated and previously generated)
- Unselected sections are NOT included in export, even if they were previously generated
- This allows users to create focused exports of specific sections

## Technical Implementation

### New Files

```
src/anki_gen/commands/run.py       # Main run command implementation
src/anki_gen/tui/                  # TUI components (optional, could use questionary/rich)
  ├── file_selector.py             # File picker widget
  ├── section_selector.py          # Section multi-select with depth toggle
  └── config_editor.py             # Configuration form
```

### Dependencies

Consider adding for interactive TUI:
- `questionary` - Interactive prompts (already cross-platform)
- OR use `rich` prompts + custom key handling

### CLI Signature

```python
@app.command()
def run(
    book_path: Annotated[
        Path | None,
        typer.Argument(
            help="Path to book file (PDF/EPUB). If omitted, shows file picker.",
        ),
    ] = None,
    non_interactive: Annotated[
        bool,
        typer.Option(
            "--yes", "-y",
            help="Skip confirmations, use all defaults",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force", "-f",
            help="Force regenerate all sections (ignore already-generated)",
        ),
    ] = False,
) -> None:
    """Interactive wizard to parse, generate, and export flashcards."""
```

**Non-interactive mode (`--yes`) defaults:**
- Selects ALL sections at maximum depth level
- Deck hierarchy: Maximum depth (most granular deck names)
- Output directory: current directory (`./`)
- Model: `gemini-3-pro-preview`
- Deck name: Auto-generated
- Max cards: Unlimited
- Tags: None
- Skip already-generated sections (unless `--force` specified or book file changed)
- Export format: `anki-txt` (fixed, not configurable)

**Requires book path in non-interactive mode** - `anki-gen run --yes` without a book path will error.

**Example usage:**
```bash
anki-gen run book.pdf --yes           # Process all, skip already-generated
anki-gen run book.pdf --yes --force   # Regenerate everything
```

### Key Functions

```python
def scan_for_books(directory: Path) -> list[Path]:
    """Find all .pdf and .epub files in directory."""

def get_section_tree(parsed: ParsedBook, max_depth: int) -> SectionTree:
    """Build hierarchical section tree with status info."""

def get_generation_status(chapters_dir: Path) -> dict[int, str]:
    """Check which sections have been generated."""

def run_pipeline(
    book_path: Path,
    sections: list[int],
    config: RunConfig,
    console: Console,
) -> None:
    """Execute parse → generate → export pipeline."""
```

### Data Structures

```python
@dataclass
class RunConfig:
    output_dir: Path = Path(".")
    model: str = "gemini-3-pro-preview"
    deck_name: str | None = None  # None = auto
    max_cards: int | None = None  # None = unlimited
    tags: list[str] = field(default_factory=list)
    force_regenerate: bool = False
    selected_sections: list[int] = field(default_factory=list)
    depth_level: int = 1

@dataclass
class SectionNode:
    index: int
    title: str
    word_count: int
    level: int
    status: Literal["done", "pending", "partial"]
    children: list[SectionNode]
    selected: bool = False  # Default unselected per initial state requirement
```

## Edge Cases

1. **No books found** - Show friendly message suggesting supported formats
2. **Book already fully generated** - Show status in Step 2; if all selected sections are already done AND skip-regenerate is enabled, offer shortcut: "All sections already generated. [E] Re-export only  [R] Regenerate anyway  [B] Back"
3. **Invalid output directory** - Warn and fall back to current directory
4. **API errors during generation** - Show error, offer to retry or skip section
5. **Ctrl+C interrupt** - Gracefully stop, show what was completed
6. **Terminal too narrow** - Gracefully degrade table display
7. **Existing chapters directory** - Always merge: keep existing sections, add newly selected ones
8. **Book file changed (hash mismatch)** - If source file has changed since last generation, force regenerate all previously generated sections (show warning to user)
9. **Depth level with flat book** - If book has no hierarchy (all Level 1), hide depth toggle
10. **Empty selection** - Block continuation with "Please select at least one section" message
11. **Parse failure** - Show error message with details, offer to retry or quit
12. **Very large book (100+ sections)** - Show warning about estimated API calls before proceeding

## Non-Goals (Future Enhancements)

- Batch processing multiple books
- Custom prompt editing
- Card preview before generation
- Direct Anki sync (requires AnkiConnect)

## Success Metrics

- User can go from `anki-gen run` to imported Anki deck in under 2 minutes
- No documentation required for basic usage
- All existing CLI functionality remains accessible via direct commands

## Testing

1. Test with no arguments (file picker)
2. Test with valid PDF/EPUB argument
3. Test with previously partially-generated book
4. Test depth level toggling
5. Test section selection/deselection hierarchy
6. Test all configuration options
7. Test interrupt handling (Ctrl+C)
