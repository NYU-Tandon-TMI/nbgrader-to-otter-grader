# nbgrader-to-otter

Converts nbgrader instructor notebooks to otter-grader format without dropping content.

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

The first cell of the source notebook must be a raw cell with `# ASSIGNMENT CONFIG` and assignment-level YAML before step 8 — the transform doesn't synthesize it. Anything else `otter assign` needs (duplicate `qN` names from sub-questions, missing markers, leftover nbgrader metadata) is flagged by `validate_structure` in steps 3 and 7; fix what it reports and re-run.

---

## Testing pipeline

Structural conversion is half the job. Once `otter assign` builds the `dist/` artifacts, a separate pipeline checks that the autograder actually runs, that no solutions leaked into the student notebook, and that the student-facing prose still makes sense after solution stripping.

```bash
SCRIPTS=skills/testing-otter-grader/scripts

# 1. Pre-flight: solution cells must have outputs
python3 $SCRIPTS/check_outputs.py homework-N.ipynb

# 2. Build (runs `otter assign` with a 300s timeout, captures logs)
python3 $SCRIPTS/run_otter_assign.py homework-N.ipynb dist/ > assign.log

# 3. Verify dist/ structure (autograder zip, student notebook, companion files)
python3 $SCRIPTS/validate_generated_output.py dist/ --config homework-N.ipynb > structure.log

# 4. Coherence check (LLM-as-judge) — see below
python3 $SCRIPTS/eval_student_coherence.py dist/student/homework-N.ipynb
# read the printed prompt, evaluate, write findings to coherence.json

# 5. Run autograder against instructor solutions — expect 100%
python3 $SCRIPTS/run_autograder_tests.py \
    dist/autograder/homework-N.ipynb \
    dist/autograder/homework-N-autograder_*.zip > autograder.log

# 6. Aggregate everything into a single report
python3 $SCRIPTS/generate_report.py \
    --notebook homework-N.ipynb \
    --assign-log assign.log \
    --structure-log structure.log \
    --student-notebook dist/student/homework-N.ipynb \
    --instructor-notebook homework-N.ipynb \
    --autograder-log autograder.log \
    --coherence coherence.json \
    --output report.json
```

If `report.json` shows `pipeline_status: "pass"`, the assignment is ready to upload to Gradescope. On failure, `summary.fix_actions` lists the prioritized changes by cell index.

### Coherence check (LLM-as-judge)

`otter assign` strips solution cells and replaces them with `# YOUR CODE HERE` placeholders. Anything those cells introduced — variable names, intermediate results, narrative setup — disappears with them. Later cells that reference the missing context become incoherent for the student even though the autograder still passes.

`eval_student_coherence.py` extracts the post-strip student notebook, prints an evaluation prompt, and stops. The reading agent (Claude in your session, or any other LLM) plays the role of a student encountering the notebook for the first time and reports gaps as JSON:

```json
[
  {"cell_index": 12, "description": "References 'model' which was never introduced", "severity": "high"},
  {"cell_index": 24, "description": "Mentions 'the previous step' but no such step exists", "severity": "medium"}
]
```

Save the output to `coherence.json` and pass it to `generate_report.py`. Findings are advisory — they appear under `stages.coherence` but never flip `pipeline_status`. High-severity gaps should be resolved by adding scaffolding cells (variable declarations, brief context paragraphs) before the question block, then re-running the conversion.

The LLM-as-judge approach catches what static validators miss: silent narrative breaks where the autograder is happy but the student is lost.

### Failure mode worth watching: trapped markdown

When an nbgrader question has the shape `solution cell → markdown cell → solution cell`, `wrap_transform` groups all three into one `BEGIN SOLUTION` / `END SOLUTION` block, and `otter assign` strips everything inside that block — including the markdown — from the student notebook. The autograder still passes, but the student loses context.

Catch it two ways: `diff_notebooks` reports the markdown cell as dropped after transform (compare counts before running `otter assign`), and the coherence check flags the resulting narrative gap in the student notebook. Fix by moving the trapped markdown cell to just before `BEGIN SOLUTION` so it sits outside the solution block.

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

## Installation

**Recommended — pin to a commit SHA** (immutable, audit-friendly, resistant to tag reassignment):

```
/plugin marketplace add NYU-Tandon-TMI/nbgrader-to-otter-grader#<commit-sha>
/plugin install nbgrader-to-otter@nbgrader-to-otter-grader
```

Get the SHA for the latest release from [GitHub Releases](https://github.com/NYU-Tandon-TMI/nbgrader-to-otter-grader/releases).

**Tag-based install** (convenient, but tags are mutable on GitHub):

```
/plugin marketplace add NYU-Tandon-TMI/nbgrader-to-otter-grader#v1.0.0
/plugin install nbgrader-to-otter@nbgrader-to-otter-grader
```

**Unpinned** (tracks `main`, not recommended for production):

```
/plugin marketplace add NYU-Tandon-TMI/nbgrader-to-otter-grader
/plugin install nbgrader-to-otter@nbgrader-to-otter-grader
```

### Updating a pinned install

```
/plugin marketplace remove nbgrader-to-otter-grader
/plugin marketplace add NYU-Tandon-TMI/nbgrader-to-otter-grader#<new-sha>
/plugin install nbgrader-to-otter@nbgrader-to-otter-grader
```

### Supply-chain notes

- All plugin scripts execute locally in your Claude Code session. Review `skills/*/scripts/*.py` before installing.
- The plugin performs no network calls, uses no `eval`/`exec`, and only invokes `subprocess.run` with list-form arguments (no shell interpolation) to call `otter`, `jupyter`, and `python3` from your local environment.
- No credentials, API keys, or secrets are stored in the repo; the plugin does not read or write any environment variables beyond what the local `otter` and `jupyter` commands require.
- Report vulnerabilities via [Security Advisories](https://github.com/NYU-Tandon-TMI/nbgrader-to-otter-grader/security/advisories/new) (see `SECURITY.md`).

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
        check_outputs.py             # Pre-flight: solution cells have outputs
        run_otter_assign.py          # Build wrapper (300s timeout)
        validate_generated_output.py # Verify dist/ structure
        eval_student_coherence.py    # LLM-as-judge coherence check
        run_autograder_tests.py      # Grade solutions against autograder zip
        run_notebook.py              # Standalone notebook executor
        generate_report.py           # Aggregate all stages into report.json
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
