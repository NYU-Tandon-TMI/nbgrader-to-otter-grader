#!/usr/bin/env python3
"""Run otter assign and capture structured output.

Input: instructor notebook path, output directory path
Output: JSON to stdout with exit_code, stdout, stderr, duration, and output paths.

Wraps `otter assign` in a subprocess with a 300-second timeout.
On failure, parses stderr for known error patterns to aid diagnosis.
"""

import glob
import json
import subprocess
import sys
import time
from pathlib import Path


# Known error patterns in otter assign stderr.
# Each tuple: (substring to match, issue_type for report)
ERROR_PATTERNS = [
    ("SyntaxError", "otter_assign_syntax"),
    ("AssertionError", "test_failure"),
    ("KeyError", "otter_assign_yaml"),
    ("yaml.scanner.ScannerError", "otter_assign_yaml"),
    ("FileNotFoundError", "otter_assign_file_missing"),
    ("No # BEGIN QUESTION found", "otter_assign_syntax"),
    ("ModuleNotFoundError", "import_error"),
    ("ImportError", "import_error"),
]


def classify_error(stderr_text):
    """Match stderr against known patterns. Returns list of matched issue_types."""
    matched = []
    for pattern, issue_type in ERROR_PATTERNS:
        if pattern in stderr_text and issue_type not in matched:
            matched.append(issue_type)
    return matched


def find_autograder_zip(output_dir):
    """Find the autograder zip in dist/autograder/."""
    ag_dir = Path(output_dir) / "autograder"
    zips = list(ag_dir.glob("*-autograder_*.zip")) + list(ag_dir.glob("*autograder*.zip"))
    if zips:
        return str(zips[0])
    return None


def run(notebook_path, output_dir):
    notebook_path = Path(notebook_path).resolve()
    output_dir = Path(output_dir).resolve()

    if not notebook_path.exists():
        return {
            "exit_code": 1,
            "stdout": "",
            "stderr": f"Notebook not found: {notebook_path}",
            "duration_seconds": 0,
            "output_dir": str(output_dir),
            "autograder_zip": None,
            "error_patterns": [],
        }

    # Run from the notebook's parent directory so relative file paths resolve
    cwd = str(notebook_path.parent)

    start = time.time()
    try:
        result = subprocess.run(
            ["otter", "assign", str(notebook_path), str(output_dir)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "otter assign timed out after 300 seconds",
            "duration_seconds": 300,
            "output_dir": str(output_dir),
            "autograder_zip": None,
            "error_patterns": [],
        }
    except FileNotFoundError:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "otter command not found. Install with: pip install otter-grader",
            "duration_seconds": 0,
            "output_dir": str(output_dir),
            "autograder_zip": None,
            "error_patterns": [],
        }

    duration = round(time.time() - start, 2)

    error_patterns = []
    if result.returncode != 0:
        error_patterns = classify_error(result.stderr)

    ag_zip = find_autograder_zip(output_dir) if result.returncode == 0 else None

    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_seconds": duration,
        "output_dir": str(output_dir),
        "autograder_zip": ag_zip,
        "error_patterns": error_patterns,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 3:
        print("Usage: run_otter_assign.py <notebook.ipynb> <output_dir>", file=sys.stderr)
        sys.exit(1)

    result = run(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2))

    # Exit 0 even on otter failure so the pipeline can continue collecting diagnostics.
    # The caller reads exit_code from the JSON to determine success.


if __name__ == "__main__":
    main()
