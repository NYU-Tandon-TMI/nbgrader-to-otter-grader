---
name: refactoring-nbgrader-to-otter
description: >
  This skill should be used when the user asks to "convert an nbgrader notebook",
  "refactor to otter-grader", "migrate from nbgrader", "create an instructor notebook",
  or mentions nbgrader-to-otter conversion, otter assign, or grading format migration.
  Operates on one notebook at a time within its containing folder.
---

# NBGrader to Otter-Grader Refactoring

<context>
NBGrader marks solution/test cells via cell metadata (`nbgrader.solution`, `nbgrader.grade`).
Otter-grader uses raw cell delimiters (`# BEGIN QUESTION`, `# BEGIN SOLUTION`, `# BEGIN TESTS`)
with inline YAML config. The transformation preserves all non-functional cells unchanged.
Only solution and test cells get restructured. The output is an instructor notebook from
which `otter assign` generates student and autograder versions.
</context>

<rules>
1. **Preserve metadata until Step 7.** The transformation scripts use `nbgrader.solution`,
   `nbgrader.grade`, and `nbgrader.points` to identify questions. Stripping metadata early
   causes "Question 'qN' not found" errors and forces manual completion.

2. **Verify files before listing in config.** Run `ls -la` before populating the `files:` key
   in assignment config. Listing non-existent files (e.g., `utils.py` when absent) causes
   `otter assign` to fail with FileNotFoundError.

3. **Validate after transform.** Run `validate_structure.py --skip-cleanup` after
   `wrap_transform.py` to catch structural issues before the eval cycle.

4. **Keep a backup.** Copy the original notebook before starting. This allows restoring and
   restarting if the workflow goes wrong.
</rules>

<environment_constraints>
- Commands use `python3` (not `python`)
- Git is not available (use file backups)
- External package installation is not available
</environment_constraints>

<spark_checklist>
If the notebook uses PySpark, confirm the following before creating `environment.yml`.
These four must be handled in a single pass — each one is a separate Gradescope failure
mode if missed.

Ask the user before proceeding:
- **What PySpark version does your JupyterHub/cluster run?** Pin that exact minor version
  (e.g. `pyspark=3.5`). Gradescope's conda-forge defaults to the latest, which may be a
  major version ahead and break the notebook.
- **What Java version is required?** Gradescope's base image has no Java installed. Pin
  the matching JDK (e.g. `openjdk=11`). Without it, PySpark cannot start.

Then verify in the notebook:
1. **JUPYTERHUB_USER**: any `os.environ['JUPYTERHUB_USER']` must become
   `os.environ.get('JUPYTERHUB_USER', 'grader')` — the key is absent on Gradescope.
2. **Spark output directories**: JupyterHub writes Spark output as a directory of part
   files (e.g. `output.csv/part-00000.csv`). The autograder zip needs a single file.
   Copy only the part file:
   ```bash
   cp shared/<assignment>/output.csv/part-*.csv <assignment>/output.csv
   ```
</spark_checklist>

<workflow>
Copy this checklist and track progress in a scratchpad file:

```
- [ ] Step 0: Backup original notebook, create scratchpad
- [ ] Step 1: Scan working directory, verify files
- [ ] Step 2: Analyze notebook structure (analyze_notebook.py)
- [ ] Step 3: Insert assignment config (raw cell at index 0)
- [ ] Step 4: Run wrap_transform.py (single pass, all questions)
- [ ] Step 5: Eval cycle (max 3 iterations)
- [ ] Step 6: Save instructor notebook, rename original to -nbgrader.ipynb
- [ ] Step 7: Strip metadata + full validation
```

### Step 0: Backup and initialize scratchpad

```bash
cp <notebook>.ipynb <notebook>-original.ipynb
touch <notebook-stem>-scratchpad.md
```

Populate the scratchpad with the template from [references/scratchpad-template.md](references/scratchpad-template.md).
Update it incrementally after each step. The scratchpad survives context compaction and
provides an audit trail for the Testing Agent.

### Step 1: Scan working directory

```bash
ls -la
```

Identify companion files (`.csv`, `.json`, `.txt`, `.md`, `.png`, `utils.py`) for the
assignment config `files:` key. Only list files that actually exist.

If the notebook imports PySpark, complete the `<spark_checklist>` now — before Step 3.
The PySpark and Java versions must be confirmed before writing `environment.yml`.

### Step 2: Analyze notebook structure

```bash
python3 scripts/analyze_notebook.py <notebook.ipynb>
```

Read the full JSON output to understand the notebook before transforming anything.

### Step 3: Insert assignment config

Insert a raw cell at index 0. Template: [references/assignment-config-template.md](references/assignment-config-template.md).

Verify each file exists before listing:
```bash
ls utils.py data-card.md diagram.png
```

Only `name:` and `files:` change per notebook.

### Step 4: Run wrap_transform.py

Single pass transforms all questions at once:

```bash
python3 scripts/wrap_transform.py <notebook.ipynb>
```

### Step 5: Eval cycle (max 3 iterations)

```
5a: python3 scripts/validate_structure.py --skip-cleanup <notebook.ipynb>
5b: python3 scripts/diff_notebooks.py <original-nbgrader.ipynb> <notebook.ipynb>
5c: If both pass → done
5d: If diff fails → python3 scripts/fix_cells.py <original-nbgrader.ipynb> <notebook.ipynb> <report.json>
5e: If validate fails → flag for manual review
5f: Abort if dropped+misplaced count did not decrease from previous iteration
```

Update the scratchpad after each iteration with validation and diff results.

### Step 6: Save instructor notebook

Write the transformed notebook as `{name}.ipynb` (NOT `{name}-instructor.ipynb`). Otter
assign uses the input filename for the student notebook — naming it `-instructor` would
expose that name to students. Rename the original nbgrader notebook to
`{name}-nbgrader.ipynb` or `{name}-original.ipynb` as backup. Preserve existing cell
outputs. Do not execute — that is the Testing Agent's responsibility.

### Step 7: Strip metadata + full validation

After the eval cycle passes, remove nbgrader metadata and run full validation:

```bash
python3 scripts/cleanup_metadata.py <notebook>.ipynb
python3 scripts/validate_structure.py <notebook>.ipynb
```

This removes `cell.metadata.nbgrader`, orphaned markers, and placeholder assignments.
Running this earlier breaks the transformation scripts — keep it as the final step.
</workflow>

<structural_rules>
All delimiter cells are raw cells (not code, not markdown). Nesting order:

```
QUESTION
  ├── SOLUTION
  └── TESTS
```

SOLUTION and TESTS are siblings inside QUESTION. Question config format:

```yaml
# BEGIN QUESTION
name: qN
points: P
all_or_nothing: true
```

Place `# BEGIN QUESTION` before the first solution cell, after the question's markdown
header and any read-only setup code.
</structural_rules>

<context_management>
This is a long task that may consume significant context. Save the scratchpad frequently
to persist progress. Work systematically — accuracy over speed. If approaching output
limits, ensure the current question transformation is complete and validated before stopping.
The scratchpad allows pausing and resuming without losing progress.
</context_management>

## Reference Files

- **[references/refactoring-rules.md](references/refactoring-rules.md)** — Cell classification, marker rules, edge cases
- **[references/assignment-config-template.md](references/assignment-config-template.md)** — Fixed YAML template
- **[references/scratchpad-template.md](references/scratchpad-template.md)** — Scratchpad structure
- **[references/transformation-patterns.py](references/transformation-patterns.py)** — Code patterns for manual transforms
- **[references/troubleshooting.md](references/troubleshooting.md)** — Common otter-grader pitfalls

<critical_pitfalls>
1. **Execute the notebook before `otter assign`.** Otter parses cell outputs to generate
   test doctests. Missing outputs cause `NameError` failures in the autograder because
   solution variables are never defined. Execute locally with:
   ```bash
   cd {notebook_dir}
   jupyter nbconvert --to notebook --execute --inplace \
       --ExecutePreprocessor.allow_errors=True {name}.ipynb
   ```
   The `--allow-errors` flag lets `grader.check_all()` cells fail harmlessly while
   solution cells still produce outputs. No JupyterHub needed.

2. **Resolve shared data paths locally.** Notebooks may reference absolute paths like
   `~/shared/<assignment-name>/`. Create symlinks to the downloaded data:
   ```bash
   ln -s /path/to/downloaded/data/<assignment-name> ~/shared/<assignment-name>
   ```
   Without these, data-loading cells fail silently under `--allow-errors`, and all
   downstream solution cells produce empty outputs that cascade into NameErrors.

3. **Always include `environment: environment.yml` in the assignment config.** Create an
   `environment.yml` in the notebook directory listing all required packages. Gradescope
   uses this to replicate the execution environment. Without it, otter auto-generates a
   minimal environment that may lack packages (scipy, seaborn, etc.), causing ImportError
   or different numerical results on Gradescope.

   Scan **both the notebook AND every bundled `.py` helper file** for imports. A helper
   module like `helper_functions.py` may import `seaborn`, `networkx`, or other packages
   not used directly in the notebook. If any of these are missing from `environment.yml`,
   `import helper_functions` fails on Gradescope — and because it is in the same cell as
   `import os, pathlib` and the path setup, ALL subsequent imports in that cell are lost.
   Symptoms look like a data-loading failure (`NameError: path_data not defined`), not a
   missing package. This is a silent cascade that is easy to misdiagnose.

   Checklist before uploading to Gradescope:
   ```bash
   # list every import in all bundled .py helper files
   grep -h "^import\|^from" *.py | sort -u
   ```
   Also scan the notebook imports visually or via:
   ```bash
   jupyter nbconvert --to script {name}.ipynb --stdout 2>/dev/null | grep "^import\|^from" | sort -u
   ```
   Cross-reference both against `environment.yml` and add any gaps.

4. **Test cells must be self-contained.** If a test references variables defined outside
   its `# BEGIN QUESTION` / `# END QUESTION` block, the autograder will fail with
   NameError. Either move the data setup inside the test cell, or wrap dependent
   assertions in try/except (air-gap pattern).

5. **Provided computation cells must live inside the question block, before `# BEGIN TESTS`.**
   A common NBGrader pattern is: student writes `means` and `standard_deviations` (solution
   cells), then a provided non-solution cell computes `ratings_pivot_table_standardized`
   from those values, and then the test checks `ratings_pivot_table_standardized`. During
   conversion, the provided computation cell often ends up AFTER `# END QUESTION`. When
   otter runs the test, the computation has not executed yet and the test fails with
   NameError. Fix: move any provided computation cell that produces a tested variable to
   between `# END SOLUTION` and `# BEGIN TESTS` inside the question block.
</critical_pitfalls>

## Pre-Flight Check

Before handing off to the Testing Agent, verify outputs exist:

```bash
python3 scripts/check_outputs.py {name}.ipynb
```

If any solution cells lack outputs, execute locally (see critical pitfall #1 above).
Ensure shared data symlinks are in place first (critical pitfall #2). This script
is in the testing-otter-grader skill's scripts directory.
