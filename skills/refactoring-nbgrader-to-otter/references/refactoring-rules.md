# NBGrader â†’ Otter Grader: Refactoring Rules

## Overview

Transform a single nbgrader-formatted Jupyter notebook into an otter-grader instructor notebook. The instructor notebook is the "source of truth" from which `otter assign` generates student and autograder versions.

Working directory: the folder containing the notebook, companion datasets, `utils.py`, and `environment.yml`.

## Cell Classification

Every cell in an nbgrader notebook falls into one of three categories:

| Category | Detection | Action |
|----------|-----------|--------|
| Solution cell | `cell.metadata.nbgrader.solution == True` | Refactor with otter markers |
| Test cell | `cell.metadata.nbgrader.grade == True` | Refactor with otter markers |
| Non-functional cell | Neither flag set | Pass through unchanged |

Non-functional cells include markdown exposition, read-only code, and instructional text. Do not alter them.

## Notebook-Level Changes

### 1. Insert Assignment Config (cell index 0)

Insert a **raw cell** as the first cell. Content:

```yaml
# ASSIGNMENT CONFIG
name: {notebook-stem}
environment: environment.yml
files:
  - utils.py
  - {dataset1}
  - {dataset2}
solutions_pdf: false
export_cell:
  pdf: false
generate:
  pdf: false
  use_submission_pdf: false
  filtering: true
  pagebreaks: true
  zips: false
  show_stdout: false
  show_hidden: false
```

Rules for `files:`:
- Always include `utils.py`
- Scan CWD for data files (`.csv`, `.json`, `.txt`, `.md`, etc.) referenced by the notebook
- Include any file imported or loaded in the notebook code cells
- Paths are relative to the notebook directory

The `environment:` value is always `environment.yml`. All other config keys stay fixed across notebooks.

### 2. Question Name Assignment

Question names follow the pattern `q1`, `q2`, ..., `qN`. Derive the number from the markdown header preceding the solution cell:

```
### Question 3: Similarity  â†’  q3
```

Parse the integer from `### Question {N}:` in the nearest preceding markdown cell. If no header is found, auto-increment.

Do NOT use `cell.metadata.nbgrader.grade_id` values (they are auto-generated hashes like `cell-f86a06f57e235aa1`).

Do NOT use HTML anchor `name` attributes (they are unreliable/duplicated in practice).

### 3. Points Extraction

Points are stored on **test cells** (grade=True), not solution cells:

```python
cell.metadata.nbgrader.points  # integer, typically 1
```

If a question has multiple test cells, sum their points.

## Question-Level Transformation

A "question" in nbgrader is the group of: preceding markdown context â†’ solution cell(s) â†’ test cell(s). In otter-grader, this maps to a structured block bounded by raw cells.

### Otter Question Block Structure

```
[raw]  # BEGIN QUESTION
       name: qN
       points: P
       all_or_nothing: true

... non-functional cells (markdown prompts, read-only code) stay in place ...

[raw]  # BEGIN SOLUTION
[code] solution code with # SOLUTION markers
... possibly interleaved markdown cells ...
[code] more solution code with # SOLUTION markers
[raw]  # END SOLUTION

... non-functional cells between solution and tests stay in place ...

[raw]  # BEGIN TESTS
[code] visible test assertions
[code] # HIDDEN
       hidden test assertions
[raw]  # END TESTS

[raw]  # END QUESTION
```

### Placing BEGIN QUESTION

Insert the `# BEGIN QUESTION` raw cell BEFORE the first solution cell of the question, but AFTER the question's markdown header and any read-only setup code that students need.

Guideline: the `# BEGIN QUESTION` goes right before the first solution cell (or the first markdown prompt cell that directly precedes it within the question scope).

### Solution Cell Transformation

**Input (nbgrader):**
```python
q1 = ...

### BEGIN SOLUTION ###
q1 = (768,)
### END SOLUTION ###
```

**Output (otter):**
```python
q1 = (768,) # SOLUTION
```

Transformation rules:
1. Remove placeholder lines: `q1 = ...`, bare `...`, bare `â€¦`
2. Remove nbgrader markers: `### BEGIN SOLUTION`, `### END SOLUTION` (with any trailing `###` or whitespace variations)
3. Extract the actual solution code
4. Apply `# SOLUTION` markers per the rules below

### # SOLUTION Marker Rules

**Simple assignment (one line):** Append `# SOLUTION` to the line.
```python
q1 = (768,) # SOLUTION
```

**Multi-line block (function body, loop, etc.):** Wrap with `# BEGIN SOLUTION` / `# END SOLUTION`. Do NOT add `# SOLUTION` to individual lines inside the block.
```python
# BEGIN SOLUTION
radius = 3
area = radius * pi * pi
# END SOLUTION
```

**Multiple solution cells in one question:** If a question has multiple solution cells separated by non-functional cells (markdown, read-only code), wrap ALL of them in a single `# BEGIN SOLUTION` / `# END SOLUTION` pair. Non-functional cells between them stay in place inside the solution block.

Example (Q5 pattern):
```
[raw]  # BEGIN SOLUTION
[code] euclidean_distance = np.linalg.norm(...) # SOLUTION
[md]   Calculate the cosine distance...
[code] cosine_distance = 1 - np.dot(...) # SOLUTION
[raw]  # END SOLUTION
```

### Test Cell Transformation

**Input (nbgrader):**
```python
# TEST

assert type(q1) == tuple

### BEGIN HIDDEN TESTS
assert q1 == (768,)
### END HIDDEN TESTS
```

**Output (otter):** Split into separate code cells within `# BEGIN TESTS` / `# END TESTS`:

Visible test cell:
```python
assert type(q1) == tuple
```

Hidden test cell:
```python
# HIDDEN
assert q1 == (768,)
```

Transformation rules:
1. Remove `# TEST` / `#TEST` comment lines
2. Split on `### BEGIN HIDDEN TESTS` / `### END HIDDEN TESTS` (with whitespace/hash variations)
3. Visible assertions â†’ one code cell
4. Hidden assertions â†’ one code cell, first line must be `# HIDDEN` (with space after `#`)
5. Skip blank lines and pure comment lines (except `# HIDDEN` marker)
6. If a question has multiple contiguous test cells, aggregate: combine all visible tests into one cell, all hidden tests into another

### Handling Edge Cases

**Test cell with no hidden tests:** Only emit the visible test cell (no `# HIDDEN` cell).

**Test cell with only hidden tests:** Only emit the hidden cell with `# HIDDEN` prefix.

**Solution cell with no corresponding test:** Still wrap in BEGIN/END QUESTION and BEGIN/END SOLUTION. Omit the BEGIN/END TESTS block.

**Zero-point questions:** Use `points: 0` in the question config. Still emit the full question structure.

**Non-graded questions (no solution, no test cells):** Do not wrap. Pass through as-is.

## Deterministic vs LLM-Assisted Decision

For each question, choose ONE approach:

### Use Deterministic When:
- Solution is a single variable assignment: `qN = <value>`
- Value is a literal: string, number, tuple, boolean, list of literals
- No multi-line logic, no function definitions, no complex expressions
- Test cells have straightforward assert patterns

Deterministic transformation is a mechanical text substitution. It cannot fail if the pattern matches.

### Use LLM-Assisted When:
- Solution contains multi-line logic (function bodies, loops, conditional blocks)
- Solution involves computation that could be simplified
- Multiple solution cells need to be reasoned about together
- Tests reference computed values or complex expressions
- The student version needs meaningful signposting (not just `...` everywhere)

The LLM should preserve semantics while potentially simplifying the solution (e.g., collapsing intermediate variables if the result is clearer).

## Structural Validation Checklist

After transformation, verify:

- [ ] Cell 0 is a raw cell starting with `# ASSIGNMENT CONFIG`
- [ ] Every `# BEGIN QUESTION` has a matching `# END QUESTION`
- [ ] Every `# BEGIN SOLUTION` has a matching `# END SOLUTION`
- [ ] Every `# BEGIN TESTS` has a matching `# END TESTS`
- [ ] All delimiter cells are raw cells (not code, not markdown)
- [ ] Question nesting: SOLUTION and TESTS blocks are inside QUESTION blocks
- [ ] No orphaned nbgrader markers remain (`### BEGIN SOLUTION`, `### BEGIN HIDDEN TESTS`, etc.)
- [ ] No placeholder artifacts remain (`q1 = ...`, bare `...`)
- [ ] All `cell.metadata.nbgrader` removed from every cell (otter-grader does not use metadata)
- [ ] `# HIDDEN` marker has exactly one space after `#`
- [ ] All `files:` entries in ASSIGNMENT CONFIG exist in CWD
- [ ] Non-functional cells are unmodified

## NBGrader Marker Patterns to Strip

These patterns appear in nbgrader source and must be removed during transformation:

```
### BEGIN SOLUTION ###
### END SOLUTION ###
### BEGIN SOLUTION
### END SOLUTION
### BEGIN HIDDEN TESTS
### END HIDDEN TESTS
###BEGIN HIDDEN TESTS
###END HIDDEN TESTS
# BEGIN HIDDEN TESTS
# END HIDDEN TESTS
#BEGIN HIDDEN TESTS
#END HIDDEN TESTS
# TEST
#TEST
```

Also remove any line matching: `{variable_name} = ...` (placeholder assignment with ellipsis).

## Metadata Cleanup

Otter-grader does not use cell metadata by convention. After reading `cell.metadata.nbgrader` to plan each question's transformation (identifying solution/test cells, extracting points), delete the entire `nbgrader` key from `cell.metadata`. This applies to every cell in the notebook, not just solution/test cells.
