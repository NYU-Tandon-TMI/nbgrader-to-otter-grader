# nbgrader-to-otter v2.0

Converts nbgrader instructor notebooks to otter-grader format without dropping content. The core guarantee: every non-functional cell in the original appears in the converted output, or the pipeline tells you exactly which ones are missing and fixes them.

---

## How it works

nbgrader marks solution and test cells via notebook metadata (`cell.metadata.nbgrader.solution`, `.grade`). otter-grader uses raw cell delimiters (`# BEGIN QUESTION`, `# BEGIN SOLUTION`, etc.) with inline YAML config. The conversion has three phases:

**1. Transform** — `wrap_transform.py` wraps each nbgrader question group in otter delimiters, strips solution markers from solution cells, and splits test cells into visible and hidden portions. Markdown, code, and other non-functional cells are never deleted.

**2. Evaluate** — `diff_notebooks.py` compares original and converted notebooks: normalized exact match first, fuzzy match (SequenceMatcher ≥ 0.85) for cells ≥ 20 chars. Reports dropped cells and structural gaps (code cells between question blocks).

**3. Fix** — `fix_cells.py` reinserts any dropped cells at their original relative positions and relocates structurally misplaced code cells inside the nearest question block.

Steps 2–3 repeat (max 3 iterations, monotonicity check) until the diff passes.

---

## Workflow

### Standard conversion

```bash
SCRIPTS=skills/refactoring-nbgrader-to-otter/scripts

# 1. Make a working copy
cp homework-N-nbgrader.ipynb homework-N.ipynb

# 2. Transform
python3 $SCRIPTS/wrap_transform.py homework-N.ipynb

# 3. Validate structure (skip metadata check during iteration)
python3 $SCRIPTS/validate_structure.py homework-N.ipynb --skip-cleanup

# 4. Content diff vs original
python3 $SCRIPTS/diff_notebooks.py homework-N-nbgrader.ipynb homework-N.ipynb

# 5. If diff fails, fix and re-diff (repeat until pass or max 3 iterations)
python3 $SCRIPTS/fix_cells.py homework-N-nbgrader.ipynb homework-N.ipynb report.json
python3 $SCRIPTS/diff_notebooks.py homework-N-nbgrader.ipynb homework-N.ipynb

# 6. Final cleanup (strip remaining nbgrader metadata)
python3 $SCRIPTS/cleanup_metadata.py homework-N.ipynb

# 7. Full validation (includes metadata check)
python3 $SCRIPTS/validate_structure.py homework-N.ipynb

# 8. Build with otter
otter assign homework-N.ipynb dist --no-run-tests
```

### After transform — manual fixes always required

The pipeline handles structural conversion, but two things need human review every time:

**Duplicate question names.** The transform derives question names from section headers (`### Question 2` → `q2`). Sub-questions (`### Question 2.2` → also `q2`) collide. `validate_structure` reports these; rename them in the raw delimiter cells (`name: q2_2`).

**ASSIGNMENT CONFIG.** The first cell must be a raw cell with `# ASSIGNMENT CONFIG` and assignment-level YAML. The transform does not create this. Add it manually before running `otter assign`.

---

## Scripts

All scripts live in `skills/refactoring-nbgrader-to-otter/scripts/`. They share `_lib.py`.

### `wrap_transform.py`

Transforms a pure nbgrader notebook in place. Detects question groups by pairing `nbgrader.solution` cells with their preceding `nbgrader.grade` cells, finds the associated question header (any heading level matching `Question N`), and wraps the group in otter raw cell delimiters.

```
python3 wrap_transform.py <notebook.ipynb>
```

Output: modifies the notebook in place, prints a summary of questions found.

Idempotent — safe to run twice.

### `diff_notebooks.py`

Compares an original nbgrader notebook against a converted one. Excludes solution cells, test cells, and otter infrastructure from comparison (these are expected to change). Reports:

- `dropped_cells` — non-functional cells from original with no match in converted
- `misplaced_cells` — code cells between question blocks, or question headers outside blocks

```
python3 diff_notebooks.py <original.ipynb> <converted.ipynb>
# Structural analysis only (no original needed):
python3 diff_notebooks.py --converted-only <converted.ipynb>
```

Exits 0 on pass, 1 on fail. JSON to stdout.

### `fix_cells.py`

Reads a diff report (JSON from `diff_notebooks.py`) and applies fixes:

- Dropped cells: reinserted at their original relative position using an anchor map (highest-index preceding matched cell)
- Misplaced code cells: moved to just before `# END QUESTION` of the nearest preceding question block

Strips `nbgrader` metadata from reinserted cells; preserves everything else.

```
python3 fix_cells.py <original.ipynb> <converted.ipynb> <report.json>
```

Modifies the converted notebook in place.

### `validate_structure.py`

Checks otter structural requirements:

1. ASSIGNMENT CONFIG present as first raw cell
2. `BEGIN QUESTION` / `END QUESTION` pairs balanced
3. `BEGIN SOLUTION` / `END SOLUTION` inside every question
4. `BEGIN TESTS` / `END TESTS` present (when test cells exist)
5. No duplicate question names
6. No leftover nbgrader metadata (skipped with `--skip-cleanup`)

```
python3 validate_structure.py <notebook.ipynb> [--skip-cleanup]
```

Exits 0 on pass, 1 on fail. JSON to stdout.

### `cleanup_metadata.py`

Strips `nbgrader` keys from all cell metadata. Run after the diff loop passes, before final validation.

```
python3 cleanup_metadata.py <notebook.ipynb>
```

### `analyze_notebook.py`

Inspection utility. Prints cell-by-cell summary with types, nbgrader flags, and source previews. Useful for understanding a notebook before conversion.

```
python3 analyze_notebook.py <notebook.ipynb>
```

---

## Testing

47 unit and integration tests across 6 modules.

```bash
cd nbgrader-to-otter
python3 tests/run_tests.py
```

Or by module:

```bash
python3 -m pytest tests/test_lib.py tests/test_wrap_transform.py tests/test_diff_notebooks.py tests/test_fix_cells.py tests/test_validate_structure.py tests/test_pipeline.py -v
```

Test coverage includes:
- `test_lib.py` — `_lib.py` primitives: cell detection, header search, marker stripping, delimiter identification
- `test_wrap_transform.py` — transform correctness: question blocks created, solution markers added, nbgrader markers stripped, cell order preserved, idempotence
- `test_diff_notebooks.py` — diff logic: exact match, fuzzy match, short-cell exact-only, solution/test exclusion, structural gap detection
- `test_fix_cells.py` — reinsertion and relocation, metadata stripping, original metadata preservation
- `test_validate_structure.py` — each validation category, `--skip-cleanup` flag
- `test_pipeline.py` — end-to-end: transform → diff → fix loop on all fixture notebooks

---

## Known limitations

**Sub-question naming.** Headers like `### Question 3.2` produce `q3` — the regex captures only the leading integer. Collision is detected by `validate_structure`; fix by manually editing the `name:` field in the delimiter cell.

**Embedded question headers.** When a markdown cell contains both prose and a question header (e.g., a transition paragraph ending with `#### Question 2.2`), `diff_notebooks` flags it as a question header outside a question block. This is a correct structural observation — the header should be in its own cell. Low priority unless otter assign fails on it.

**ASSIGNMENT CONFIG not generated.** The transform has no way to infer assignment-level metadata (name, seed, etc.). Always add this manually.

**First-cell type.** If the original notebook starts with a markdown title cell, `validate_structure` will flag it. Convert to raw and add `# ASSIGNMENT CONFIG` content above it, or insert a new raw cell before it.

**Multi-solution question groups.** If a question has more than one solution cell (e.g., a sub-part), the transform wraps them together. Verify the `BEGIN SOLUTION` / `END SOLUTION` pair covers the intended cell range.

---

## Installation

```bash
claude plugin marketplace add NYU-Tandon-TMI/nbgrader-to-otter-grader
claude plugin install nbgrader-to-otter@nbgrader-to-otter-grader
```

Or via slash command inside Claude Code:

```
/plugin marketplace add NYU-Tandon-TMI/nbgrader-to-otter-grader
/plugin install nbgrader-to-otter@nbgrader-to-otter-grader
```

---

## File structure

```
nbgrader-to-otter-grader/
  skills/
    refactoring-nbgrader-to-otter/
      scripts/
        _lib.py                    # Shared utilities (no side effects)
        wrap_transform.py          # Phase 1: nbgrader → otter delimiters
        diff_notebooks.py          # Phase 2: content verification
        fix_cells.py               # Phase 3: auto-repair
        validate_structure.py      # Structural validation
        cleanup_metadata.py        # Metadata scrub
        analyze_notebook.py        # Inspection utility
      references/
        refactoring-rules.md
        transformation-patterns.py
        troubleshooting.md
    testing-otter-grader/
      scripts/
        eval_student_coherence.py  # LLM-as-student coherence check
        run_otter_assign.py
        check_outputs.py
  agents/
    notebook-converter.md          # Orchestrator agent
    refactoring-agent.md
    testing-agent.md
  tests/
    fixtures.py                    # Shared notebook builders
    test_lib.py
    test_wrap_transform.py
    test_diff_notebooks.py
    test_fix_cells.py
    test_validate_structure.py
    test_pipeline.py
```
