# Troubleshooting

## Diagnosing "variable not defined" failures on Gradescope

When a test fails with `NameError: variable_name not defined`, work through this checklist
in order. Multiple layers produce identical-looking symptoms:

1. **Check imports first.** Did `import helper_functions` (or any bundled `.py`) fail
   because one of ITS imports (e.g. `seaborn`) is missing from `environment.yml`? A
   failed top-level import cascades to everything below it in the same cell — including
   `import os, pathlib` and the entire path setup. Symptom looks like a data-loading
   failure, not a missing package. Fix: grep every bundled `.py` file for imports and
   cross-reference against `environment.yml`.

2. **Check path setup.** Is `_local = pathlib.Path('.')` used (correct) or
   `pathlib.Path(os.path.dirname(os.path.abspath('__file__')))` (broken)? In a Jupyter
   kernel, `'__file__'` is a string literal, not the notebook path. Fix:
   ```python
   _local = pathlib.Path('.')  # CWD — where otter copies bundled files
   ```

3. **Check data load.** Does `pd.read_csv(path_data)` succeed? If path setup failed,
   data never loads and all downstream variables cascade to NameError.

4. **Check cell order.** Is the tested variable produced by a provided (non-solution)
   computation cell that sits AFTER `# END QUESTION`? It hasn't run when the test fires.

---

### Issue: Transitive import missing from environment.yml

**Symptom**: `NameError: path_data not defined` (or any variable after the import block).
Works locally, fails on Gradescope.

**Cause**: A bundled helper module (e.g. `helper_functions.py`) imports a package
(e.g. `seaborn`) that is not in `environment.yml`. `import helper_functions` fails.
Because `import os, pathlib` and the path setup are in the SAME import cell, they also
fail. Your local environment (conda base, Docker image, or system Python) likely has the
package installed already, so the failure only surfaces on Gradescope where the
environment is built strictly from `environment.yml`.

**Fix**: Add the missing package to `environment.yml`. To audit:
```bash
grep -h "^import\|^from" *.py | sort -u
```
Cross-reference every result against `environment.yml`.

---

### Issue: Provided computation cell placed after END QUESTION

**Symptom**: `NameError: derived_variable not defined` in the test, even though the
student's solution cells (which produce the inputs) are correct.

**Cause**: NBGrader notebooks often have this pattern: student computes `means` and
`standard_deviations` (solution cells), then a provided non-solution cell computes
`standardized_table = (data - means) / standard_deviations`, and then the test checks
`standardized_table`. During conversion the provided cell typically lands AFTER
`# END QUESTION`, so it hasn't executed when the test fires.

**Fix**: Move the provided computation cell to inside the question block, between
`# END SOLUTION` and `# BEGIN TESTS`.

---

## Common Issues

**Cell outputs cleared before `otter assign`**: Otter parses cell outputs to generate test
doctests. If you run `otter assign` on a notebook with cleared outputs, every test expects
no output, causing false failures. The Refactoring Agent preserves existing outputs but does
NOT execute the notebook to generate missing ones. If outputs are missing, the Testing Agent
handles re-execution before running `otter assign`.

**Public tests failing in student notebook**: Before running the last cell (`grader.export()`),
save the notebook first (Ctrl+S), then run the cell.

**Error running `grader.export()` in student notebook**: Same fix. Save the notebook before
running the export cell.

**File format errors**: Only `.ipynb` files in proper nbgrader structure are supported.
Verify the notebook has `cell.metadata.nbgrader` on solution/test cells.

**`otter assign` produces errors about missing files**: Every entry in the `files:` list
of the assignment config must exist in the notebook's directory. Check paths are relative
and files are present.

**YAML parse errors in raw cells**: Assignment config and question config raw cells must
contain valid YAML. Common mistakes: tabs instead of spaces, missing colons, unquoted
strings with special characters.

**Delimiter cell is wrong type**: All `# BEGIN QUESTION`, `# END QUESTION`, `# BEGIN SOLUTION`,
`# END SOLUTION`, `# BEGIN TESTS`, `# END TESTS` cells must be **raw cells**. If they are
code or markdown cells, `otter assign` will not recognize them.

**`# HIDDEN` marker not recognized**: The marker must be exactly `# HIDDEN` with one space
after `#`. Variants like `#HIDDEN` or `## HIDDEN` will not work.

**Leaked solutions in student notebook**: If a solution line is missing the `# SOLUTION`
marker (or the solution block is missing `# BEGIN SOLUTION` / `# END SOLUTION` comment
wrappers), `otter assign` will not strip it from the student version.

## Metadata Issues

### Issue: "Question 'qN' not found in notebook"

**Symptoms**:
- `wrap_transform.py` exits with error
- Message: "Question 'q2' not found in notebook"

**Cause**:
Nbgrader metadata was stripped before running `wrap_transform.py`. The script relies on
`cell.metadata.nbgrader` to identify solution and test cells.

**Solution**:
1. Restore from backup: `cp notebook-original.ipynb notebook.ipynb`
2. Restart workflow from Step 0
3. Run `wrap_transform.py` before `cleanup_metadata.py` (Step 4 before Step 7)

**Prevention**:
- Never run `cleanup_metadata.py` until the eval cycle (Step 5) passes
- `wrap_transform.py` preserves metadata automatically — use `cleanup_metadata.py` as Step 7

### Issue: Metadata still present after transformation

**Symptoms**:
- After running `otter assign`, you see warnings about nbgrader metadata
- Cell metadata still contains `nbgrader` keys

**Cause**:
You used `--keep-metadata` flag and forgot to run the final cleanup step.

**Solution**:
Run the cleanup utility:
```bash
python3 scripts/cleanup_metadata.py {name}.ipynb
```

This is Step 8 (FINAL STEP) of the workflow and should only be run after ALL questions are transformed.
