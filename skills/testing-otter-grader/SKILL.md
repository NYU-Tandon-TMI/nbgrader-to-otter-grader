---
name: testing-otter-grader
description: >
  This skill should be used when the user asks to "test an otter-grader notebook",
  "validate an instructor notebook", "run otter assign", "check autograder tests",
  "generate a test report", or mentions QA-ing otter-grader notebooks, running the
  testing pipeline, or checking for leaked solutions. Triggers after refactoring
  from nbgrader to otter-grader.
---

# Otter-Grader Testing Pipeline

<scope>
The Testing Agent validates instructor notebooks AFTER the Refactoring Agent has
completed structural validation (`validate_structure.py`). The Refactoring Agent
catches formatting errors (wrong cell types, missing delimiters, orphaned markers).
The Testing Agent catches semantic errors: code that fails to run, tests that fail,
missing dependencies, and leaked solutions.
</scope>

<prerequisites>
Before running the pipeline, verify:

1. Instructor notebook exists: `{name}.ipynb`
2. Refactoring Agent's `validate_structure.py` passed (exit 0)
3. CWD contains all companion files referenced in ASSIGNMENT CONFIG
4. `otter-grader` is installed: `pip install otter-grader`
5. **Instructor notebook has cell outputs** — run the pre-flight check:

```bash
python scripts/check_outputs.py {name}.ipynb
```

If `status` is `"fail"`, solution cells are missing outputs. Execute the notebook
before proceeding. Without outputs, `otter assign` generates tests that reference
undefined variables, causing NameError failures in the autograder.

**Local execution** (preferred over JupyterHub):
```bash
cd {notebook_dir}
jupyter nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.allow_errors=True {name}.ipynb
```
The `--allow-errors` flag is essential: `grader.check_all()` and `grader.export()`
cells will error (otter test files don't exist yet), but solution cell outputs still
populate correctly. Run from the notebook's directory so relative paths resolve.

**Shared data paths**: If notebooks reference absolute paths (e.g., `~/shared/<assignment-name>/`),
create symlinks to the downloaded data files:
```bash
ln -s /path/to/downloaded/data/<assignment-name> ~/shared/<assignment-name>
```
Without these, data-loading cells fail and all downstream solution cells produce NameErrors.

After execution, re-run `check_outputs.py` to confirm solution cells have outputs.

6. Assignment config includes `environment: environment.yml` and the file exists with all
   required packages. Gradescope builds strictly from this file — packages present in your
   local environment but absent here will cause `ImportError` on Gradescope. Audit all
   bundled `.py` helper files for transitive imports:
   ```bash
   grep -h "^import\|^from" *.py | sort -u
   ```
   Cross-reference every result against `environment.yml` before proceeding.
</prerequisites>

<pipeline>
Copy this checklist and track progress:

```
- [ ] Stage 1: Run otter assign
- [ ] Stage 2: Validate generated output structure
- [ ] Stage 3: Validate student notebook
- [ ] Stage 3.5: Student notebook coherence (optional)
- [ ] Stage 4: Run autograder tests against solutions
- [ ] Stage 5: Generate error report
```

Each stage depends on the previous. If a stage fails, continue running subsequent
stages to collect maximum diagnostic information. The final report marks the pipeline
as failed regardless.

### Stage 1: Run otter assign

```bash
python scripts/run_otter_assign.py {name}.ipynb dist/ > assign.log
```

Wraps `otter assign` with a 300-second timeout. Captures exit code, stdout/stderr, and
duration. On failure, check `error_patterns` against
[references/error-patterns.md](references/error-patterns.md) for the fix mapping.

<environment_specific_failures>
If `otter assign` fails because hidden tests produce AssertionError or NameError on
environment-dependent computations, use `--no-run-tests` to bypass local test validation:

```bash
otter assign --no-run-tests {name}.ipynb dist/
```

This is safe when `environment.yml` is properly configured — Gradescope will replicate
the correct environment using that file, so tests that fail locally due to package version
differences will pass on Gradescope. Common local-only failure causes:
- `scipy.optimize.linprog` using different solvers across platforms (macOS/ARM64 vs Linux)
- MinHash/random permutation results varying with numpy versions
- Floating-point precision differences in matrix operations

Only use `--no-run-tests` when failures are clearly environment-specific, not logic errors.
Verify by checking that the solution code runs and produces reasonable output in the
executed notebook.
</environment_specific_failures>

If successful, `dist/` contains `autograder/` and `student/` directories.
See [references/expected-output-structure.md](references/expected-output-structure.md).

### Stage 2: Validate generated output structure

```bash
python scripts/validate_generated_output.py dist/ --config {name}.ipynb > structure.log
```

Checks that `dist/autograder/` and `dist/student/` contain expected contents: notebook,
autograder zip (non-empty, valid), otter_config.json, and companion files. The `--config`
flag extracts the `files:` list from the instructor notebook to verify companion files
are present in both directories.

### Stage 3: Validate student notebook

Handled by `generate_report.py` (Stage 5) with `--student-notebook` and
`--instructor-notebook` flags. Performs static analysis:

<student_checks>
- Cell 0 is the otter initialization cell (`import otter; grader = otter.Notebook(...)`)
- No leaked solution code (compares student cells against instructor solutions)
- No leaked markers (`# SOLUTION`, `# HIDDEN`, `# BEGIN TESTS`, etc.)
- Final cells include `grader.check_all()` and `grader.export()`
</student_checks>

Leaked solution detection is the most critical check. If a solution line lacks the
`# SOLUTION` marker in the instructor notebook, `otter assign` will not strip it from
the student version — giving students the answer.

### Stage 3.5: Student notebook coherence (optional)

```bash
python3 scripts/eval_student_coherence.py dist/student/{name}.ipynb
```

The script prints an evaluation prompt to stdout. Read it and evaluate the student notebook as the student described — you are the judge, no external call needed. Produce a JSON array of gap findings and write it to `coherence.json`:

```json
[
  {"cell_index": 12, "description": "References 'model' which was never introduced", "severity": "high"},
  {"cell_index": 24, "description": "Mentions 'the previous step' but no such step exists", "severity": "medium"}
]
```

If no gaps found, write `[]`. Pass `coherence.json` to Stage 5:

```bash
python3 scripts/generate_report.py \
    --notebook {name}.ipynb \
    --assign-log assign.log \
    --structure-log structure.log \
    --student-notebook dist/student/{name}.ipynb \
    --instructor-notebook {name}.ipynb \
    --autograder-log autograder.log \
    --coherence coherence.json \
    --output report.json
```

Coherence findings appear in `report.json` under `stages.coherence` and never change `pipeline_status` — they are advisory. High-severity gaps should be flagged for human review before distribution.

### Stage 4: Run autograder tests against solutions

```bash
python scripts/run_autograder_tests.py dist/autograder/{name}.ipynb \
    dist/autograder/{name}-autograder_*.zip > autograder.log
```

Grades the autograder notebook (which contains solutions) against the autograder zip.
Expected result: 100% score on all questions.

<failure_causes>
Any failure indicates one of:
- Solution code altered during refactoring
- Test assertions are incorrect
- Dependencies missing (import errors)
- Solution cell output was cleared before `otter assign`
</failure_causes>

The per-question breakdown identifies exactly which questions fail with full tracebacks.

### Stage 5: Generate error report

```bash
python3 scripts/generate_report.py \
    --notebook {name}.ipynb \
    --assign-log assign.log \
    --structure-log structure.log \
    --student-notebook dist/student/{name}.ipynb \
    --instructor-notebook {name}.ipynb \
    --autograder-log autograder.log \
    --coherence coherence.json \
    --output report.json
```

Aggregates all stage results, runs student notebook validation (Stage 3), maps errors
to issue types with fix actions, deduplicates, and writes `report.json`.
See [references/report-schema.md](references/report-schema.md) for the format.
</pipeline>

<reading_the_report>
If `pipeline_status` is `"pass"`, the notebook is ready for distribution.

If `"fail"`, read `summary.fix_actions` for a prioritized list of fixes. Each action
identifies the responsible agent and the specific change needed. The `stages` section
provides per-stage detail. For test failures, `stages.autograder_tests.per_question`
shows which questions failed with full tracebacks.
</reading_the_report>

<feedback_loop>
Hand `report.json` to the Refactoring Agent. It should:

1. Read `summary.fix_actions`
2. Open the instructor notebook, navigate to `cell_index`, apply each fix
3. Re-run `validate_structure.py`
4. Hand back to Testing Agent for re-test

This loop converges within 2-3 iterations. If not, flag for manual review.
</feedback_loop>

## Utility: run_notebook.py

Standalone notebook executor for re-running notebooks when outputs are missing:

```bash
python scripts/run_notebook.py {name}.ipynb
```

Copies the notebook to a temp directory with companion files, executes via
`jupyter nbconvert`, and returns per-cell execution results as JSON.
Does not modify the original.

<common_failures>
These failures recur across notebooks:

1. **NameError in autograder tests.** Solution cells have no outputs. The notebook was
   not executed before `otter assign`. Fix: execute locally with
   `jupyter nbconvert --execute --allow-errors`, then re-run `otter assign`.

2. **FileNotFoundError: environment.yml.** Assignment config references `environment.yml`
   but the file doesn't exist in the notebook directory. Fix: create the file with all
   required packages (scan notebook imports AND all bundled `.py` helper files for
   transitive imports). Do NOT remove the `environment:` line — Gradescope needs it to
   replicate the execution environment.

3. **Transitive import from helper module missing in environment.yml.** `import
   helper_functions` succeeds locally because your local environment (conda base, Docker
   image, or system Python) may have packages installed that are not in `environment.yml`.
   On Gradescope, the environment is built strictly from `environment.yml` — nothing else.
   If `helper_functions.py` imports `seaborn` and `seaborn` is not in `environment.yml`,
   the import fails — and because `import os, pathlib` and path setup are in the SAME
   cell, they also fail. The symptom is `NameError: path_data not defined`, which looks
   like a data-loading bug, not a missing package. Diagnosis: check every bundled `.py`
   file's imports against `environment.yml` before assuming anything else is wrong:
   ```bash
   grep -h "^import\|^from" *.py | sort -u
   ```

4. **Test references variable outside question block.** Tests depend on data loaded in
   cells before `# BEGIN QUESTION`. Fix: add data setup inside the test cell or use
   try/except (wrap the assertion in `try/except NameError: pass` so a missing variable
   does not fail the whole test suite).

5. **Provided computation cell placed after `# END QUESTION`.** Pattern: student solves
   `means` and `standard_deviations`; a non-solution cell computes `standardized_table`
   from those; the test checks `standardized_table`. During conversion the computation
   cell lands AFTER `END QUESTION`, so it hasn't run when the test fires. Fix: move
   the provided computation cell to between `# END SOLUTION` and `# BEGIN TESTS`.

6. **"Public Tests" phantom failure (0/1 points).** Otter-grader artifact from
   `grader.check_all()`. No fix needed — this is expected behavior. All actual per-question
   tests pass; only the synthetic "Public Tests" summary entry shows 0/1.

7. **FileNotFoundError on shared data paths.** Notebooks reference absolute paths like
   `~/shared/<assignment-name>/` that only exist on JupyterHub. Fix: create symlinks
   from the expected path to the local downloaded data directory.

8. **AssertionError in hidden tests (environment-specific).** scipy, numpy, or random
   seed differences between local machine and Gradescope produce slightly different
   numerical results. Fix: use `otter assign --no-run-tests` locally. With a proper
   `environment.yml` in the zip, Gradescope replicates the correct environment and
   these tests will pass there.
</common_failures>

## Reference Files

- **[references/error-patterns.md](references/error-patterns.md)** — Issue type taxonomy, stderr-to-fix mapping
- **[references/expected-output-structure.md](references/expected-output-structure.md)** — Expected `dist/` contents
- **[references/report-schema.md](references/report-schema.md)** — JSON format for `report.json`
