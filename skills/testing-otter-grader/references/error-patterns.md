# Error Patterns and Fix Actions

## Issue Type Taxonomy

Each issue has a `issue_type` that identifies the error category, the pipeline stage
where it's detected, and who is responsible for fixing it.

| issue_type | Stage | Fix Owner | Fix Action |
|------------|-------|-----------|------------|
| `otter_assign_syntax` | 1 | Refactoring Agent | Fix code in the identified cell |
| `otter_assign_yaml` | 1 | Refactoring Agent | Fix YAML in assignment or question config |
| `otter_assign_file_missing` | 1 | Refactoring Agent | Update `files:` list in ASSIGNMENT CONFIG |
| `missing_autograder_dir` | 2 | Re-run pipeline | otter assign may have failed silently |
| `missing_student_dir` | 2 | Re-run pipeline | otter assign may have failed silently |
| `missing_otter_init` | 3 | Manual review | Verify ASSIGNMENT CONFIG is valid |
| `leaked_solution` | 3 | Refactoring Agent | Add `# SOLUTION` marker to solution line |
| `missing_grader_check` | 3 | Manual review | Likely an otter assign bug |
| `leaked_marker` | 3 | Refactoring Agent | Check raw cell type and content |
| `missing_export_cells` | 3 | Manual review | Verify ASSIGNMENT CONFIG export settings |
| `test_failure` | 4 | Refactoring Agent | Fix solution code or test assertions |
| `import_error` | 4 | Refactoring Agent | Add missing package to `environment.yml` (not `files:` — that is for data/helper files, not Python packages) |
| `output_mismatch` | 4 | Re-run prerequisite | Re-execute notebook with outputs before otter assign |
| `execution_error` | 4 | Refactoring Agent | Check notebook dependencies and cell order |

## Common otter assign Error Patterns

These stderr patterns from `otter assign` map to specific issue types:

| stderr contains | issue_type | Likely cause |
|----------------|------------|--------------|
| `SyntaxError` | `otter_assign_syntax` | Malformed code in solution or test cell |
| `AssertionError` | `test_failure` | Solution doesn't pass its own tests |
| `KeyError: 'name'` | `otter_assign_yaml` | Missing `name:` in BEGIN QUESTION YAML |
| `yaml.scanner.ScannerError` | `otter_assign_yaml` | Invalid YAML in raw cell |
| `FileNotFoundError` | `otter_assign_file_missing` | File in `files:` not in CWD |
| `No # BEGIN QUESTION found` | `otter_assign_syntax` | Missing question delimiters |
| `ModuleNotFoundError` | `import_error` | Missing Python package |
| `ImportError` | `import_error` | Missing Python package or module |

## Diagnosing NameError failures — ordered checklist

When Stage 4 reports `NameError: X not defined`, do NOT assume a single cause. Work through
these layers in order:

| Layer | What to check | Symptom if broken |
|-------|--------------|-------------------|
| 1. Transitive import | Does any bundled `.py` file import a package not in `environment.yml`? | `import helper_module` fails; path setup in same cell also fails → looks like data-loading failure |
| 2. Path setup | Is `_local = pathlib.Path('.')` correct (not `os.path.dirname(os.path.abspath('__file__'))`)?  | `path_data` undefined → data never loads |
| 3. Data load | Does `pd.read_csv(path_data)` succeed? | All downstream variables NameError |
| 4. Cell order | Is the tested variable produced by a provided cell AFTER `# END QUESTION`? | Variable not defined at test time |

Layer 1 is the hardest to spot because your local environment (conda base, Docker image,
or system Python) may have the package pre-installed, making the failure invisible locally.
Gradescope builds strictly from `environment.yml` — nothing else carries over. Always grep
bundled `.py` files:
```bash
grep -h "^import\|^from" *.py | sort -u
```

## Feedback Loop

See `<feedback_loop>` in `testing-otter-grader/SKILL.md` for the full process. In brief:
apply each `fix_action` from `report.json`, re-run `validate_structure.py`, then re-test.
Converges within 2–3 iterations; flag for manual review if not.
