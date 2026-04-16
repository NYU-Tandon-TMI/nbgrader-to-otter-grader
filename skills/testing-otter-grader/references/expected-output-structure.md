# Expected Output Structure

## dist/ Directory After otter assign

A successful `otter assign` produces this structure:

```
dist/
├── autograder/
│   ├── {name}.ipynb              # Instructor notebook with solutions intact
│   ├── {name}-autograder_*.zip   # Autograder configuration zip
│   ├── otter_config.json         # Autograder settings
│   ├── utils.py                  # Companion files copied from CWD
│   └── {datasets}                # Data files listed in ASSIGNMENT CONFIG
└── student/
    ├── {name}.ipynb              # Student notebook (solutions stripped)
    ├── utils.py                  # Companion files copied from CWD
    └── {datasets}                # Data files listed in ASSIGNMENT CONFIG
```

`{name}` is the notebook stem (e.g., `homework-0` from `homework-0-instructor.ipynb`).

## Student Notebook Structure

The generated student notebook should have:

1. **Cell 0**: Otter initialization
   ```python
   # Initialize Otter
   import otter
   grader = otter.Notebook("homework-0.ipynb")
   ```

2. **Question cells**: For each question, solution code is replaced with placeholder (`...`).
   After each question's code cell, a `grader.check("qN")` cell appears.

3. **No leaked markers**: None of these should appear anywhere in the student notebook:
   `# SOLUTION`, `# BEGIN SOLUTION`, `# END SOLUTION`, `# HIDDEN`,
   `# BEGIN TESTS`, `# END TESTS`, `# BEGIN QUESTION`, `# END QUESTION`,
   `### BEGIN SOLUTION`, `### END SOLUTION`, `### BEGIN HIDDEN TESTS`,
   `### END HIDDEN TESTS`

4. **Final cells**: `grader.check_all()` followed by `grader.export(...)`.

## Autograder Zip Contents

The autograder zip (`{name}-autograder_*.zip`) is used by `otter run` and Gradescope.
It contains test files, configuration, and requirements. It should be non-empty and
a valid zip file. The Testing Agent does not inspect its internal structure beyond
verifying it exists and is valid.
