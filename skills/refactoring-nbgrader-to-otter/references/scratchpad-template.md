# Refactoring Progress: {notebook-stem}

**Created**: {timestamp}
**Notebook**: {notebook-stem}.ipynb
**Status**: IN_PROGRESS

## Checklist

- [ ] Step 0: Backup original notebook & create scratchpad
- [ ] Step 1: Scan working directory & verify files
- [ ] Step 2: Analyze notebook structure
- [ ] Step 3: Insert assignment config (verify files!)
- [ ] Step 4: Run wrap_transform.py
- [ ] Step 5: Eval cycle (validate → diff → fix, max 3 iterations)
- [ ] Step 6: cleanup_metadata.py
- [ ] Step 7: Final validate_structure.py

## Assignment Metadata

- **Notebook**: {notebook-stem}.ipynb
- **Backup**: {notebook-stem}-nbgrader.ipynb
- **Companion Files**: [list from Step 1]
- **Total Questions**: [from Step 2]

## Questions Status

| Question | Status | Validation | Notes |
|----------|--------|-----------|-------|
| q1 | pending | - | |
| q2 | pending | - | |

*Update this table during Step 5 eval cycle*

## Detailed Progress

### Step 0: Backup & Scratchpad
- [ ] Created {notebook-stem}-nbgrader.ipynb
- [ ] Created {notebook-stem}-scratchpad.md

### Step 1: File Verification
- [ ] Scanned directory: `ls -la`
- Companion files identified:
  - [ ] [file 1]
  - [ ] [file 2]

### Step 2: Analysis
- [ ] Ran `python3 scripts/analyze_notebook.py {notebook-stem}.ipynb`
- [ ] Total questions: [N]
- [ ] Analysis output captured below

```json
{paste analyze_notebook.py JSON output here}
```

### Step 3: Assignment Config
- [ ] Inserted config cell at index 0
- [ ] Verified all files in `files:` list exist in CWD
- Files included in config:
  - [ ] [verified file 1]
  - [ ] [verified file 2]

### Step 4: wrap_transform.py
- [ ] Ran `python3 scripts/wrap_transform.py {notebook-stem}.ipynb`
- Questions wrapped: [N]

### Step 5: Eval Cycle

**Iteration 1**
- validate_structure.py: [PASS/FAIL]
- diff_notebooks.py: [PASS/FAIL — dropped: N, misplaced: N]
- fix_cells.py: [run if diff failed]

**Iteration 2** (if needed)
- validate_structure.py: [PASS/FAIL]
- diff_notebooks.py: [PASS/FAIL]

**Iteration 3** (if needed)
- validate_structure.py: [PASS/FAIL]
- diff_notebooks.py: [PASS/FAIL]

### Step 6: Metadata Cleanup
- [ ] Ran `python3 scripts/cleanup_metadata.py {notebook-stem}.ipynb`

### Step 7: Final Validation
- [ ] Ran `python3 scripts/validate_structure.py {notebook-stem}.ipynb`
- [ ] Exit 0, all checks pass

```json
{paste final validation output}
```

## Errors & Recoveries

| Issue | Step | Solution | Status |
|-------|------|----------|--------|
| [description] | [N] | [fix applied] | resolved |

## Final Summary

- **Completion Status**: [IN_PROGRESS/COMPLETED/FAILED]
- **Iterations Required**: [N]
- **Issues Encountered**: [count]
- **Next Step**: [e.g., "Hand off to Testing Agent" or "Manual: fix duplicate question names"]

---

*Last Updated*: {timestamp}
