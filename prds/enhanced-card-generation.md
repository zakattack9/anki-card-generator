# PRD: Enhanced Flashcard Generation

## Overview

Enhance the `anki-gen generate` command to produce a single, well-organized Anki import file that combines both basic and cloze card types with improved metadata for organization, searchability, and re-import support.

## Current State

- Generates separate files per card type: `chapter_XXX_basic.txt`, `chapter_XXX_cloze.txt`
- Two separate API calls per chapter (one for basic, one for cloze)
- Significant content duplication between card types (~40 duplicate facts observed)
- No deck specification in output files
- No tags for organization
- No GUID support for re-importing/updating cards
- Manual deck selection required during Anki import

## Proposed State

- Single combined file per chapter: `chapter_XXX_cards.txt`
- **Single API call** with unified prompt (AI decides card type per fact)
- **Zero duplication** - each fact appears once in optimal format
- File headers specify deck, tags, and column mappings
- Per-card tags for topic categorization
- GUID column for re-import/update support
- Hierarchical deck structure based on book/chapter

---

## Unified Prompt Strategy

### Problem Analysis

Review of generated cards revealed:
- **~40 duplicate facts** across basic and cloze files for the same chapter
- Many basic cards that would be better as cloze (simple number/name recall)
- Some cloze cards that would be better as basic (complex explanations)
- Excessive cloze deletions (up to 4 per card)

### Solution: Single Unified Prompt

Replace separate `BASIC_CARD_PROMPT` and `CLOZE_CARD_PROMPT` with a single `UNIFIED_CARD_PROMPT` that:
1. Generates both card types in one API call
2. Lets AI decide optimal card type per fact
3. Enforces strict deduplication
4. Produces higher quality cards

### Card Type Selection Criteria

The AI should select card type based on these rules:

**USE CLOZE WHEN:**
| Scenario | Example |
|----------|---------|
| Single number, date, or percentage | "House capped at {{c1::435}} members" |
| Named person, place, or document | "{{c1::Julius and Ethel Rosenberg}} were executed" |
| Specific terminology | "The {{c1::Supremacy}} Clause declares..." |
| Article/Section references | "Article {{c1::III}} establishes the judiciary" |
| Sentence reads naturally with blank | Fill-in-blank feels natural |

**USE BASIC WHEN:**
| Scenario | Example |
|----------|---------|
| Answer requires explanation | "Why did framers give Senators six-year terms?" |
| Answer has multiple parts/list | "What are the three branches?" → list answer |
| Definition requiring context | "What does it mean to impeach?" |
| Comparison or contrast | "How does X differ from Y?" |
| Process or procedure | "How are vacancies filled?" |

### Quality Constraints

1. **Maximum 2 cloze deletions** per card (c1, c2 only)
2. **One atomic fact** per card
3. **No duplicate facts** across card types
4. **Self-contained cards** (no assumed prior knowledge)
5. **Consistent formatting** (HTML tags, math notation)

### Benefits

| Metric | Before | After |
|--------|--------|-------|
| API calls per chapter | 2 | 1 |
| Duplicate facts | ~40 per chapter | 0 |
| Generation time | ~2x | ~1x |
| API cost | ~2x | ~1x |

---

## Unified Prompt Template

```text
You are a world-class Anki flashcard creator. Generate high-quality flashcards from the chapter below.

## Card Type Selection

For EACH fact, choose the optimal card type:

**CLOZE** - Use for:
- Numbers, dates, percentages (e.g., "The House has {{c1::435}} members")
- Names of people, places, documents (e.g., "{{c1::Thomas Jefferson}} wrote...")
- Terminology and clause names (e.g., "The {{c1::Supremacy}} Clause...")
- Simple factual associations where fill-in-blank reads naturally

**BASIC** - Use for:
- "Why" or "How" questions requiring explanation
- Answers with multiple parts or lists
- Definitions needing full context
- Comparisons or contrasts
- Processes or procedures

## Rules

1. Each fact appears ONCE - no duplicates between card types
2. Maximum 2 cloze deletions per card ({{c1::...}} and {{c2::...}} only)
3. One atomic fact per card
4. Cards must be self-contained (no assumed prior knowledge)
5. Use your knowledge to add context that makes cards complete

{max_cards_instruction}

## Output Format

Each card on a new line with pipe separator:
- Basic: `Basic|Question|Answer|tags`
- Cloze: `Cloze|Cloze text with {{c1::deletions}}|Back extra info|tags`

Tags: 1-3 lowercase topic words, space-separated (e.g., "constitution amendment-process")

Formatting:
- Math: \( inline \) or \[ block \]
- Chemistry: \( \ce{H2O} \)
- Lists within fields: use <br> (no actual newlines)
- Bold: <b>text</b>, Italic: <i>text</i>

Return ONLY the cards, no other text.

## Chapter Title: {chapter_title}

## Chapter Content:
{chapter_content}
```

---

## Output Format Specification

### File Headers (Anki 2.1.54+)

```text
#separator:Pipe
#html:true
#deck:{Book Title}::Chapter {N} - {Chapter Title}
#tags:anki-gen {book-slug}
#notetype column:1
#tags column:4
#guid column:5
#columns:Note Type|Field 1|Field 2|Tags|GUID
```

### Card Row Format

```text
{NoteType}|{Field1}|{Field2}|{Tags}|{GUID}
```

Where:
- **NoteType**: `Basic` or `Cloze`
- **Field1**: Question (Basic) or Cloze text (Cloze)
- **Field2**: Answer (Basic) or Back Extra (Cloze)
- **Tags**: Space-separated topic tags (AI-generated)
- **GUID**: Unique identifier for re-import support

### Example Output

```text
#separator:Pipe
#html:true
#deck:American Government::Chapter 01 - The Birth of a Nation
#tags:anki-gen american-government
#notetype column:1
#tags column:4
#guid column:5
#columns:Note Type|Field 1|Field 2|Tags|GUID
Basic|What are the two primary goals of the Preamble?|1. Define the Constitution's purpose<br>2. Establish that authority rests with the people|preamble constitution|ch01-001
Cloze|The Constitution establishes {{c1::three}} branches of government.|Legislative, Executive, Judicial|branches constitution|ch01-002
Cloze|The House of Representatives is capped at {{c1::435}} members.|Set by Reapportionment Act of 1929|house-of-representatives congress|ch01-003
Basic|Why did the framers give Senators six-year terms?|To insulate them from "popular passions of the day" and short-term electoral politics|senate terms framers-intent|ch01-004
Cloze|To win the presidency, a candidate needs {{c1::270}} electoral votes.|Majority of 538 total electors|electoral-college presidency|ch01-005
```

---

## Implementation Plan

### Phase 1: Unified Prompt Implementation

**File**: `src/anki_gen/core/flashcard_generator.py`

- [ ] Remove `BASIC_CARD_PROMPT` constant
- [ ] Remove `CLOZE_CARD_PROMPT` constant
- [ ] Add `UNIFIED_CARD_PROMPT` constant (see template above)
- [ ] Remove `generate_basic()` method
- [ ] Remove `generate_cloze()` method
- [ ] Update `generate()` to use single prompt
- [ ] Update `_build_prompt()` to use unified template

### Phase 2: Update Parsing Logic

**File**: `src/anki_gen/core/flashcard_generator.py`

- [ ] Create `_parse_unified_output()` method:
  ```python
  def _parse_unified_output(self, response_text: str) -> tuple[list[BasicCard], list[ClozeCard]]:
      basic_cards = []
      cloze_cards = []
      for line in response_text.strip().split("\n"):
          if not line.strip() or "|" not in line:
              continue
          parts = line.split("|")
          if len(parts) >= 3:
              card_type = parts[0].strip()
              if card_type == "Basic":
                  basic_cards.append(BasicCard(...))
              elif card_type == "Cloze":
                  cloze_cards.append(ClozeCard(...))
      return basic_cards, cloze_cards
  ```
- [ ] Extract tags from 4th field
- [ ] Handle missing fields gracefully

### Phase 3: Update Data Models

**File**: `src/anki_gen/models/flashcard.py`

- [ ] Add `tags: list[str] = []` field to `BasicCard`
- [ ] Add `tags: list[str] = []` field to `ClozeCard`
- [ ] Add `guid: str = ""` field to both card models
- [ ] Add `AnkiExportConfig` model:
  ```python
  class AnkiExportConfig(BaseModel):
      deck_name: str
      global_tags: list[str] = []
      book_slug: str
      chapter_id: str
  ```
- [ ] Update `GenerationResult` with `to_combined_txt(config: AnkiExportConfig)` method

### Phase 4: GUID Generation

**File**: `src/anki_gen/core/flashcard_generator.py`

- [ ] Implement GUID generation in parsing:
  ```python
  # Format: {chapter_id}-{sequence_number}
  # Example: ch01-001, ch01-002, ch01-003
  ```
- [ ] Sequential numbering across both card types
- [ ] GUIDs assigned during parsing (not by AI)

### Phase 5: Update Export Logic

**File**: `src/anki_gen/commands/generate.py`

- [ ] Update `save_generation_result()`:
  - Output single `chapter_XXX_cards.txt` file
  - Include file headers
  - Remove `_basic.txt` and `_cloze.txt` generation
- [ ] Load book metadata from manifest for deck name
- [ ] Generate book slug from title
- [ ] Create `AnkiExportConfig` from metadata

### Phase 6: CLI Enhancements

**File**: `src/anki_gen/cli.py`

- [ ] Add `--deck` option to override default deck name
- [ ] Add `--tags` option to add extra global tags
- [ ] Update help text to reflect new single-file output

### Phase 7: Update Streaming Display

**File**: `src/anki_gen/core/flashcard_generator.py`

- [ ] Update streaming panel title to "Generating cards" (not "basic" or "cloze")
- [ ] Single streaming session per chapter

---

## File Changes Summary

| File | Changes |
|------|---------|
| `core/flashcard_generator.py` | Replace dual prompts with unified; update parsing; single API call |
| `models/flashcard.py` | Add tags, guid fields; add AnkiExportConfig; add to_combined_txt() |
| `commands/generate.py` | Single file output; deck name derivation; remove dual file generation |
| `cli.py` | Add --deck, --tags options |

---

## Migration Notes

- Existing `_basic.txt` and `_cloze.txt` files will no longer be generated
- Old dual-prompt code fully removed (no legacy mode)
- New output is `_cards.txt` with combined content
- Requires Anki 2.1.54+ for file headers support
- Card count may differ (no duplicates = fewer total cards, but same coverage)
- Manifest.json required in chapters directory for book metadata

---

## Testing Checklist

- [ ] Single API call generates both card types
- [ ] No duplicate facts between basic and cloze cards
- [ ] Card type selection matches criteria (numbers=cloze, explanations=basic)
- [ ] Maximum 2 cloze deletions enforced
- [ ] Tags extracted correctly from AI output
- [ ] GUIDs generated sequentially
- [ ] Combined file imports correctly into Anki
- [ ] Deck hierarchy created (Book::Chapter)
- [ ] Global and per-card tags applied
- [ ] Re-import with GUID updates existing cards
- [ ] Special characters handled (pipes in content)

---

## Finalized Decisions

| Item | Decision |
|------|----------|
| Legacy code | Remove completely, no `--legacy` flag |
| Chapter padding | Zero-pad to 2 digits (`ch01`, `ch02`, ... `ch99`) |
| Special characters | Sanitize titles for deck names (remove `::` and special chars) |
| Max cards | Total cards (AI decides mix within limit) |
| Manifest | Required; error if missing |
| Tag sanitization | Auto-sanitize (lowercase, hyphens, alphanumeric only) |
| Chapter ID source | From filename (e.g., `chapter_011` → `ch011`) |
| Malformed lines | Skip with warning, continue processing |
| Zero cards | Warn but don't error |
| GUID format | `{chapter_id}-{sequence}` (e.g., `ch011-001`, `ch011-002`) |
| Deck hierarchy | `{Book Title}::Chapter {NN} - {Chapter Title}` |

---

## Future Enhancements (Out of Scope)

- [ ] `anki-gen export` - Combine multiple chapter files into single deck export
- [ ] Custom note type support (beyond Basic/Cloze)
- [ ] Image/media extraction from EPUB
- [ ] Direct Anki database integration via AnkiConnect
- [ ] Card quality scoring/validation
