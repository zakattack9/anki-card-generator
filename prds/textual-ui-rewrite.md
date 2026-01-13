# PRD: Textual TUI Rewrite for Interactive `run` Command

## Overview

Rewrite the interactive `run` command wizard using [Textual](https://textual.textualize.io/) to replace the current `questionary`-based implementation. This provides a more responsive, keyboard-driven interface with proper key bindings, better scrolling for large lists, and a UI that closely matches the original PRD mockups.

## Goals

### Original PRD Goals (Preserved)
1. **Zero-friction onboarding** - New users can run `anki-gen run` with no arguments and be guided through everything
2. **Discoverability** - Users learn available options through the interactive UI rather than reading docs
3. **Smart defaults** - Sensible defaults at every step; users can accept all defaults or customize
4. **Resume support** - Detect previously generated sections and skip them by default

### New Goals (Textual Rewrite)
5. **True keyboard shortcuts** - Single-key bindings (`B`, `D`, `A`, `N`, `Space`, etc.) work directly without scrolling to select
6. **Better scrolling** - Large section lists scroll smoothly with proper viewport management
7. **Visual fidelity** - Match the PRD mockups with bordered panels, tables, and clear visual hierarchy
8. **Improved UX** - Multi-select with visible checkboxes, instant feedback, and clear navigation

## Current Problems (questionary-based)

| Problem | Root Cause | Textual Solution |
|---------|------------|------------------|
| Keyboard shortcuts don't work | `questionary.select()` doesn't support custom key bindings | Textual's `BINDINGS` class variable |
| Difficult to scroll large lists | Flat list rendering without proper viewport | `DataTable` or `SelectionList` with native scrolling |
| Skip toggle disappears | Bug in conditional rendering | Fixed state management with reactive variables |
| No clear step separation | Console clearing between prompts | Screen-based navigation with `push_screen`/`pop_screen` |

## Technical Architecture

### Dependencies

```toml
# Replace questionary with textual
dependencies = [
    # Remove: "questionary>=2.0",
    "textual>=0.50.0",  # TUI framework
]
```

### File Structure

```
src/anki_gen/
├── commands/
│   └── run.py              # Entry point, launches TUI app
├── tui/
│   ├── __init__.py
│   ├── app.py              # Main RunWizardApp class
│   ├── screens/
│   │   ├── __init__.py
│   │   ├── file_select.py   # Step 1: File selection
│   │   ├── section_select.py # Step 2: Section selection
│   │   ├── config.py        # Step 3: Configuration
│   │   ├── confirm.py       # Step 4: Confirmation
│   │   └── execute.py       # Step 5: Execution
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── section_table.py # Custom DataTable for sections
│   │   └── config_form.py   # Configuration form widget
│   └── styles.tcss          # Textual CSS stylesheet
```

## Screen Designs

### Screen 1: File Selection

```
╭─────────────────────── Select Book ───────────────────────╮
│                                                            │
│  Select a book to process:                                 │
│                                                            │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓ │
│  ┃ File                                        ┃ Size   ┃ │
│  ┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩ │
│  │ > Designing Data-Intensive Applications.pdf │ 24.4MB │ │
│  │   The Everything American Government.epub   │  1.2MB │ │
│  │   MBB2Neuro-1.pdf                           │  1.5MB │ │
│  └─────────────────────────────────────────────┴────────┘ │
│                                                            │
│  [↑↓] Navigate  [Enter] Select  [Q] Quit                   │
╰────────────────────────────────────────────────────────────╯
```

**Implementation:**
```python
class FileSelectScreen(Screen):
    BINDINGS = [
        ("enter", "select_file", "Select"),
        ("q", "quit", "Quit"),
        ("escape", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main"):
            yield Static("Select a book to process:", id="prompt")
            yield DataTable(id="file-table", cursor_type="row")
        yield Footer()
```

### Screen 2: Section Selection

```
╭──────────────────────────── Book Info ────────────────────────────╮
│ Designing Data-Intensive Applications                              │
│ Author(s): Martin Kleppmann                                        │
│ Format: PDF | Detection: PDF Outline (confidence: 95%)             │
│ Total Sections: 47 (3 levels deep)                                 │
╰────────────────────────────────────────────────────────────────────╯

Section View: Level 2 of 3

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
└────┴──────────────────────────────────────┴────────┴──────────┘

[Space] Toggle  [A] All  [N] None  [D] Depth  [Enter] Continue  [B] Back
```

**Implementation:**
```python
class SectionSelectScreen(Screen):
    BINDINGS = [
        ("space", "toggle_selection", "Toggle"),
        ("a", "select_all", "Select All"),
        ("n", "select_none", "Select None"),
        ("d", "cycle_depth", "Change Depth"),
        ("enter", "continue", "Continue"),
        ("b", "go_back", "Back"),
        ("escape", "go_back", "Back"),
        ("q", "quit", "Quit"),
    ]

    # Reactive variables for state
    depth_level = reactive(1)

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main"):
            yield Static(id="book-info")
            yield Static(id="depth-indicator")
            yield DataTable(id="section-table", cursor_type="row")
        yield Footer()

    def action_toggle_selection(self) -> None:
        """Toggle selection of current row."""
        table = self.query_one("#section-table", DataTable)
        # Toggle logic...

    def action_cycle_depth(self) -> None:
        """Cycle through depth levels."""
        self.depth_level = (self.depth_level % self.max_depth) + 1
```

**Key Features:**
- `DataTable` with native scrolling for large section lists
- Row-based cursor navigation with `↑`/`↓` keys
- Direct `Space` key toggles selection without menu navigation
- `D` key cycles depth levels instantly
- Visual checkbox state `[x]`, `[ ]`, `[~]` rendered in first column

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

**Status Column:**
- `✓ Done` - Section fully generated (has `_cards.txt`)
- `Pending` - Not yet generated
- `3/5 done` - Parent with some children generated

**Word Count Column:**
- At deeper levels: Shows word count for that specific section
- At parent levels: Shows **sum of all child sections**

**Empty Selection Handling:**
- If user presses `Enter` with 0 sections selected, show notification: "Please select at least one section"
- Block navigation to Step 3 until at least one section is selected

### Screen 3: Configuration

```
╭─────────────────────── Generation Settings ───────────────────────╮
│                                                                    │
│  Output directory:    [./                              ]           │
│  Model:               [gemini-3-pro-preview            ]           │
│  Deck name:           [Auto (Book::Part::Chapter)      ]           │
│  Max cards/section:   [Unlimited                       ]           │
│  Tags:                [(none)                          ]           │
│                                                                    │
│  ─────────────────────────────────────────────────────────────     │
│  [x] Skip already-generated sections (3 sections)                  │
│  [ ] Force regenerate all selected sections                        │
│                                                                    │
╰────────────────────────────────────────────────────────────────────╯

[Tab] Next Field  [S] Toggle Skip  [Enter] Continue  [B] Back  [Q] Quit
```

**Implementation:**
```python
class ConfigScreen(Screen):
    BINDINGS = [
        ("tab", "focus_next", "Next Field"),
        ("shift+tab", "focus_previous", "Previous Field"),
        ("s", "toggle_skip", "Toggle Skip"),
        ("enter", "continue", "Continue"),
        ("b", "go_back", "Back"),
        ("escape", "go_back", "Back"),
        ("q", "quit", "Quit"),
    ]

    skip_regenerate = reactive(True)

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="config-panel"):
            yield Input(id="output-dir", placeholder="./")
            yield Input(id="model", value="gemini-3-pro-preview")
            yield Input(id="deck-name", placeholder="Auto")
            yield Input(id="max-cards", placeholder="Unlimited")
            yield Input(id="tags", placeholder="(none)")
            yield Rule()
            with Horizontal():
                yield Checkbox(id="skip-toggle", value=True)
                yield Static("Skip already-generated sections (3 sections)")
        yield Footer()
```

**Field Behaviors:**

| Field | Default | Validation |
|-------|---------|------------|
| Output directory | Current directory (`./`) | Must exist; falls back to `./` if invalid |
| Model | `gemini-3-pro-preview` | Free text (no validation) |
| Deck name | `Auto (Book::Part::Chapter)` | Free text or "Auto" |
| Max cards/section | `Unlimited` | Positive integer or "Unlimited" |
| Tags | `(none)` | Comma-separated list |

**Deck Name Behavior:**
- `Auto`: Deck hierarchy follows selected depth level
- Custom value (e.g., `MyDeck`): ALL cards go to single deck, ignoring depth hierarchy
- Custom with `::`: User can create their own hierarchy (e.g., `Study::Biology::Chapter`)

**Regeneration Toggle:**
- Default: Skip already-generated sections
- User can toggle to force regenerate all
- Shows count of sections that will be skipped
- **Always visible** when there are sections that could be skipped (regardless of current toggle state)

### Screen 4: Confirmation

```
╭────────────────────────────── Summary ──────────────────────────────╮
│                                                                      │
│  Book:        Designing Data-Intensive Applications                  │
│  Format:      PDF (Outline detection)                                │
│                                                                      │
│  Sections:    12 selected                                            │
│    • To generate: 8 sections (at lowest level)                       │
│    • Skipping:    4 sections (already done)                          │
│                                                                      │
│  Deck depth:  Level 2 (Book::Part::Chapter)                          │
│  Output:      ./all_cards.txt                                        │
│  Model:       gemini-3-pro-preview                                   │
│  Max cards:   Unlimited                                              │
│  Tags:        (none)                                                 │
│                                                                      │
╰──────────────────────────────────────────────────────────────────────╯

Estimated sections to process: 8
This will make API calls to Gemini for each section.

                    [Enter] Start  [B] Back  [Q] Quit
```

**"All Sections Already Generated" Shortcut:**

When all selected sections are already generated AND skip-regenerate is enabled, show alternative options:

```
╭────────────────────────────── Summary ──────────────────────────────╮
│  ...                                                                 │
│  Sections:    8 selected                                             │
│    • To generate: 0 sections                                         │
│    • Skipping:    8 sections (already done)                          │
│  ...                                                                 │
╰──────────────────────────────────────────────────────────────────────╯

All selected sections are already generated!

        [E] Re-export only  [R] Regenerate anyway  [B] Back  [Q] Quit
```

**Implementation:**
```python
class ConfirmScreen(Screen):
    BINDINGS = [
        ("enter", "start_execution", "Start"),
        ("e", "export_only", "Re-export Only"),
        ("r", "regenerate_all", "Regenerate"),
        ("b", "go_back", "Back"),
        ("escape", "go_back", "Back"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="summary"):
            yield Static(id="summary-content")
            yield Static(id="warnings")
        with Horizontal(id="actions"):
            yield Button("Start", variant="primary", id="start")
            yield Button("Back", id="back")
            yield Button("Quit", variant="error", id="quit")
        yield Footer()

    def action_export_only(self) -> None:
        """Skip generation, just re-export existing cards."""
        if self.all_sections_done:
            self.app.state.config.force_regenerate = False
            self.app.push_screen("execute")

    def action_regenerate_all(self) -> None:
        """Force regenerate all sections."""
        self.app.state.config.force_regenerate = True
        self.app.push_screen("execute")
```

### Screen 5: Execution

```
Processing: Designing Data-Intensive Applications

[1/3] Parsing PDF...
  ✓ Extracted 12 sections

[2/3] Generating flashcards...
  [████████████░░░░░░░░░░░░░░░░░░░░] 3/8 sections
  Current: Chapter 6: Partitioning
  Generated: 12 basic, 8 cloze cards

[3/3] Exporting...
  ✓ Exported 245 cards to ./all_cards.txt

╭────────────────────────── Complete ──────────────────────────╮
│                                                               │
│  Total cards: 245 (142 basic, 103 cloze)                     │
│    • Newly generated: 156 cards (8 sections)                  │
│    • Previously generated: 89 cards (4 sections)              │
│                                                               │
│  Import file: ./all_cards.txt                                 │
│  Next: Import into Anki via File → Import                     │
│                                                               │
╰───────────────────────────────────────────────────────────────╯

[Enter] Done  [Q] Quit
```

**Implementation:**
```python
class ExecuteScreen(Screen):
    BINDINGS = [
        ("enter", "finish", "Done"),
        ("q", "quit", "Quit"),
        ("ctrl+c", "interrupt", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="progress"):
            yield Static(id="step-1")
            yield Static(id="step-2")
            yield ProgressBar(id="generation-progress")
            yield Static(id="current-section")
            yield Static(id="step-3")
        yield Static(id="completion-panel")
        yield Footer()

    async def run_pipeline(self) -> None:
        """Run the parse → generate → export pipeline."""
        # Update UI as each step completes
        await self.parse_book()
        await self.generate_cards()
        await self.export_cards()
```

## Main App Structure

```python
from textual.app import App
from textual.screen import Screen

class RunWizardApp(App):
    """Main application for the run wizard."""

    CSS_PATH = "styles.tcss"

    SCREENS = {
        "file_select": FileSelectScreen,
        "section_select": SectionSelectScreen,
        "config": ConfigScreen,
        "confirm": ConfirmScreen,
        "execute": ExecuteScreen,
    }

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def __init__(self, book_path: Path | None = None, **kwargs):
        super().__init__(**kwargs)
        self.book_path = book_path
        self.config = RunConfig()
        self.parsed_book: ParsedBook | None = None

    def on_mount(self) -> None:
        """Start the wizard on the appropriate screen."""
        if self.book_path:
            # Skip file selection, go directly to section selection
            self.push_screen("section_select")
        else:
            self.push_screen("file_select")
```

## CSS Stylesheet (styles.tcss)

```css
/* Global styles */
Screen {
    background: $surface;
}

Header {
    dock: top;
    height: 1;
    background: $primary;
}

Footer {
    dock: bottom;
    height: 1;
    background: $primary;
}

/* Panels */
#book-info {
    border: round $accent;
    padding: 1;
    margin: 1;
    height: auto;
}

#summary {
    border: round $success;
    padding: 1;
    margin: 1;
}

/* Tables */
DataTable {
    height: 1fr;
    margin: 1;
}

DataTable > .datatable--cursor {
    background: $accent;
    color: $text;
}

/* Checkboxes in table */
.checkbox-selected {
    color: $success;
}

.checkbox-partial {
    color: $warning;
}

.checkbox-empty {
    color: $text-muted;
}

/* Status column */
.status-done {
    color: $success;
}

.status-partial {
    color: $warning;
}

.status-pending {
    color: $text-muted;
}

/* Progress */
ProgressBar {
    margin: 1;
    padding: 1;
}

/* Buttons */
Button {
    margin: 0 1;
}

#actions {
    align: center middle;
    height: auto;
    margin: 1;
}

/* Config form */
Input {
    margin: 1;
    width: 50;
}

Checkbox {
    margin: 1;
}
```

## Navigation Flow

```
┌─────────────────┐
│  File Select    │  (No back - this is the entry point)
│    Screen 1     │
└────────┬────────┘
         │ Enter (select file)
         ▼
┌─────────────────┐
│ Section Select  │◄─────┐
│    Screen 2     │      │
└────────┬────────┘      │
         │ Enter         │ B (back)
         ▼               │
┌─────────────────┐      │
│  Configuration  │──────┤
│    Screen 3     │      │
└────────┬────────┘      │
         │ Enter         │ B (back)
         ▼               │
┌─────────────────┐      │
│  Confirmation   │──────┘
│    Screen 4     │
└────────┬────────┘
         │ Enter (start)
         ▼
┌─────────────────┐
│   Execution     │  (No back - pipeline is running)
│    Screen 5     │
└─────────────────┘
```

**Navigation Notes:**
- Screen 1 has no back navigation (it's the entry point; use `Q` to quit)
- Screen 5 has no back navigation (pipeline is running or complete)
- If book path is provided via CLI, Screen 1 is skipped entirely

## State Management

```python
@dataclass
class WizardState:
    """Shared state across all screens."""
    book_path: Path | None = None
    parsed_book: ParsedBook | None = None
    section_tree: list[SectionNode] | None = None
    config: RunConfig = field(default_factory=RunConfig)

    # Selection state
    selected_indices: set[int] = field(default_factory=set)
    depth_level: int = 1

    # Execution results
    generated_count: int = 0
    exported_count: int = 0
```

State is stored on the `App` instance and accessed by screens via `self.app.state`.

## Key Bindings Summary

**Common (All Screens):**
| Key | Action |
|-----|--------|
| `↑`/`↓` | Navigate |
| `Enter` | Confirm/Select |
| `Q` | Quit |

**Screen 1 (File Selection):**
| Key | Action |
|-----|--------|
| `Enter` | Select file |

**Screen 2 (Section Selection):**
| Key | Action |
|-----|--------|
| `Space` | Toggle selection |
| `A` | Select all |
| `N` | Select none |
| `D` | Cycle depth level |
| `B` or `Esc` | Go back |

**Screen 3 (Configuration):**
| Key | Action |
|-----|--------|
| `Tab` | Next field |
| `Shift+Tab` | Previous field |
| `S` | Toggle skip/force regenerate |
| `B` or `Esc` | Go back |

**Screen 4 (Confirmation):**
| Key | Action |
|-----|--------|
| `Enter` | Start execution |
| `E` | Re-export only (when all done) |
| `R` | Regenerate anyway (when all done) |
| `B` or `Esc` | Go back |

**Screen 5 (Execution):**
| Key | Action |
|-----|--------|
| `Ctrl+C` | Interrupt/Cancel |
| `Enter` | Done (after completion) |

## Non-Interactive Mode

Non-interactive mode (`--yes`) bypasses the TUI entirely.

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

### Non-Interactive Mode Defaults (`--yes`)

| Setting | Default Value |
|---------|---------------|
| Sections | ALL sections at maximum depth level |
| Deck hierarchy | Maximum depth (most granular deck names) |
| Output directory | Current directory (`./`) |
| Model | `gemini-3-pro-preview` |
| Deck name | Auto-generated |
| Max cards | Unlimited |
| Tags | None |
| Skip regenerate | Yes (unless `--force` specified) |
| Export format | `anki-txt` (fixed, not configurable) |

**Important:** `--yes` mode **requires** a book path argument. Running `anki-gen run --yes` without a book path will error.

### Example Usage

```bash
# Interactive mode (default)
anki-gen run                          # Shows file picker
anki-gen run book.pdf                 # Skips to section selection

# Non-interactive mode
anki-gen run book.pdf --yes           # Process all, skip already-generated
anki-gen run book.pdf --yes --force   # Regenerate everything
```

### Implementation

```python
def execute_run(
    book_path: Path | None,
    non_interactive: bool,
    force: bool,
    console: Console,
) -> None:
    if non_interactive:
        # Validate book path required
        if book_path is None:
            console.print("[red]Error: --yes requires a book path argument[/]")
            raise typer.Exit(1)
        # Run without TUI
        run_pipeline_directly(book_path, force, console)
    else:
        # Launch Textual app
        app = RunWizardApp(book_path=book_path)
        app.run()
```

## Migration Plan

1. **Phase 1: Create TUI module structure**
   - Set up `src/anki_gen/tui/` directory
   - Create base app and screen classes
   - Add `textual` dependency, remove `questionary`

2. **Phase 2: Implement screens**
   - File selection screen with DataTable
   - Section selection with custom checkbox rendering
   - Configuration form with Input widgets
   - Confirmation summary screen
   - Execution screen with ProgressBar

3. **Phase 3: Integration**
   - Wire screens together with navigation
   - Connect to existing parse/generate/export logic
   - Test full workflow

4. **Phase 4: Polish**
   - Fine-tune CSS styling
   - Add error handling and edge cases
   - Test with large books

## Testing

1. **Unit tests** for state management and business logic
2. **Integration tests** using Textual's `pilot` testing framework:
   ```python
   async def test_file_selection():
       app = RunWizardApp()
       async with app.run_test() as pilot:
           await pilot.press("down")
           await pilot.press("enter")
           assert app.screen.name == "section_select"
   ```
3. **Manual testing** with various book sizes and formats

## Success Metrics

- All keyboard shortcuts work directly (no scrolling to menu items)
- Smooth scrolling for books with 100+ sections
- UI matches PRD mockups closely
- User can complete workflow faster than with questionary
- Clear visual feedback for all actions

## Deck Hierarchy Behavior

The depth level selected in Step 2 affects deck naming:

| Depth Level | Deck Name Example |
|-------------|-------------------|
| Level 1 | `Book Title::Part I` (all chapters in Part I share same deck) |
| Level 2 | `Book Title::Part I::Chapter 1` (each chapter gets own deck) |
| Level 3 | `Book Title::Part I::Chapter 1::Section 1.1` (each section gets own deck) |

**Key Points:**
- Generation ALWAYS happens at the lowest subsection level (for maximum card quality)
- Only deck naming is affected by depth level
- Custom deck name overrides depth-based hierarchy entirely

## Export Scope

- Export includes ALL SELECTED sections (both newly generated and previously generated)
- Unselected sections are NOT included in export, even if they were previously generated
- This allows users to create focused exports of specific sections

## Edge Cases

All edge cases from the original PRD must be handled:

| # | Edge Case | Handling |
|---|-----------|----------|
| 1 | **No books found** | Show friendly message: "No PDF or EPUB files found in current directory" with exit option |
| 2 | **Book already fully generated** | Show shortcut in Step 4: "[E] Re-export only [R] Regenerate anyway" |
| 3 | **Invalid output directory** | Warn and fall back to current directory (`./`) |
| 4 | **API errors during generation** | Show error dialog with options: "[R] Retry [S] Skip section [A] Abort" |
| 5 | **Ctrl+C interrupt** | Gracefully stop, show completion panel with what was finished |
| 6 | **Terminal too narrow** | Textual handles gracefully; tables will scroll horizontally |
| 7 | **Existing chapters directory** | Merge behavior: keep existing sections, add newly selected ones |
| 8 | **Book file changed (hash mismatch)** | Show warning, force regenerate previously generated sections |
| 9 | **Depth level with flat book** | Hide depth toggle if book has no hierarchy (all Level 1) |
| 10 | **Empty selection** | Block continuation with message: "Please select at least one section" |
| 11 | **Parse failure** | Show error dialog with details, offer "[R] Retry [Q] Quit" |
| 12 | **Very large book (100+ sections)** | Show warning in Step 4 about estimated API calls |

## Error Handling

Textual provides modal dialogs for error states:

```python
class ErrorDialog(ModalScreen):
    """Modal dialog for displaying errors."""

    def __init__(self, title: str, message: str, options: list[tuple[str, str]]):
        super().__init__()
        self.title = title
        self.message = message
        self.options = options  # [(key, label), ...]

    def compose(self) -> ComposeResult:
        with Container(id="error-dialog"):
            yield Static(self.title, id="error-title")
            yield Static(self.message, id="error-message")
            with Horizontal():
                for key, label in self.options:
                    yield Button(f"[{key.upper()}] {label}", id=f"btn-{key}")
```

## References

- [Textual Documentation](https://textual.textualize.io/)
- [Textual Widget Gallery](https://textual.textualize.io/widget_gallery/)
- [Original run-command PRD](./run-command.md)
