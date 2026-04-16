# Assignment Config Template

Insert this as a **raw cell** at cell index 0. Replace `{notebook-stem}` with the notebook
filename without extension. Replace the `files:` entries with actual companion files from CWD.

```yaml
# ASSIGNMENT CONFIG
name: {notebook-stem}
environment: environment.yml
files:
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

## Rules

- `name:` is the notebook filename stem (e.g., `homework-0` for `homework-0.ipynb`)
- `environment:` must point to an `environment.yml` in the same directory as the notebook.
  This file is bundled into the autograder zip and used by Gradescope to replicate the
  execution environment. Without it, Gradescope uses a minimal default that may lack
  required packages (scipy, seaborn, etc.), causing ImportError or different numerical results.
- `files:` only include files that exist in CWD and are referenced by the notebook (e.g., `utils.py`, data files)
- Scan CWD for data files (`.csv`, `.json`, `.txt`, `.md`, etc.) referenced in notebook code cells
- Include any file imported or loaded by the notebook
- Paths are relative to the notebook directory
- All other config keys are fixed across notebooks

## environment.yml Template

Create this file in the notebook directory. Scan notebook imports to determine dependencies.

```yaml
name: otter-env
channels:
  - defaults
  - conda-forge
dependencies:
  - python=3.12
  - numpy
  - pandas
  - matplotlib
  - pip
  - jupyter_server
  - pip:
      - otter-grader[grading,plugins]==6.1.6
```

Add packages as needed: `scipy`, `seaborn`, `sqlite3` (stdlib, no install needed),
`watermark` (pip only). The environment must match what the notebook imports — otherwise
tests pass locally but fail on Gradescope with ImportError.
