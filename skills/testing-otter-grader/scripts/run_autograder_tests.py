#!/usr/bin/env python3
"""Run autograder tests against the instructor solution notebook.

Input: autograder notebook path, autograder zip path
Output: JSON to stdout with per-question scores and failure details.

Wraps `otter run -a <zip> <notebook>` and parses the output results.json.
The autograder notebook contains solutions, so 100% score is expected.
Any failure indicates a problem in the solution code or test assertions.
"""

import glob
import json
import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path


def find_results_json(search_dir):
    """Locate results.json produced by otter run.

    otter run writes results into the current directory or a temp directory.
    Search common locations.
    """
    candidates = [
        Path(search_dir) / "results.json",
        Path(search_dir) / "output" / "results.json",
    ]
    # Also glob for it
    for p in Path(search_dir).rglob("results.json"):
        candidates.append(p)

    for c in candidates:
        if c.is_file():
            return c
    return None


def parse_results(results_path):
    """Parse otter's results.json into per-question results."""
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # otter results.json format varies by version. Handle common shapes.
    per_question = {}
    total_score = 0.0
    total_possible = 0.0

    # Shape 1: {"tests": [{"name": "q1", "score": 1.0, "max_score": 1.0, ...}]}
    tests = data.get("tests", data.get("test_cases", []))
    if isinstance(tests, list):
        for t in tests:
            name = t.get("name", t.get("test_name", "unknown"))
            score = float(t.get("score", 0))
            possible = float(t.get("max_score", t.get("possible", 1)))
            total_score += score
            total_possible += possible

            entry = {
                "score": score,
                "possible": possible,
                "status": "pass" if score >= possible else "fail",
            }
            if entry["status"] == "fail":
                entry["error_type"] = t.get("error_type", "AssertionError")
                entry["traceback"] = t.get("output", t.get("traceback", ""))
            per_question[name] = entry

    # Shape 2: direct dict {"q1": {"score": ..., "possible": ...}, ...}
    elif isinstance(data, dict) and not tests:
        for name, vals in data.items():
            if isinstance(vals, dict) and "score" in vals:
                score = float(vals["score"])
                possible = float(vals.get("possible", vals.get("max_score", 1)))
                total_score += score
                total_possible += possible

                entry = {
                    "score": score,
                    "possible": possible,
                    "status": "pass" if score >= possible else "fail",
                }
                if entry["status"] == "fail":
                    entry["error_type"] = vals.get("error_type", "AssertionError")
                    entry["traceback"] = vals.get("output", vals.get("traceback", ""))
                per_question[name] = entry

    overall = "pass" if total_score >= total_possible and total_possible > 0 else "fail"

    return {
        "status": overall,
        "total_score": total_score,
        "total_possible": total_possible,
        "per_question": per_question,
    }


def run(notebook_path, zip_path):
    notebook_path = Path(notebook_path).resolve()
    zip_path = Path(zip_path).resolve()

    for p, label in [(notebook_path, "Notebook"), (zip_path, "Autograder zip")]:
        if not p.exists():
            return {
                "status": "fail",
                "total_score": 0,
                "total_possible": 0,
                "per_question": {},
                "error": f"{label} not found: {p}",
            }

    # Run otter in a temp directory to isolate output
    tmp_dir = tempfile.mkdtemp()
    try:
        # Copy notebook's companion files so imports resolve
        nb_dir = notebook_path.parent
        for f in nb_dir.iterdir():
            if f.is_file() and f.suffix != ".zip":
                shutil.copy2(f, Path(tmp_dir) / f.name)

        # Copy the notebook and zip into tmp
        tmp_nb = Path(tmp_dir) / notebook_path.name
        tmp_zip = Path(tmp_dir) / zip_path.name
        shutil.copy2(notebook_path, tmp_nb)
        shutil.copy2(zip_path, tmp_zip)

        result = subprocess.run(
            ["otter", "run", "-a", str(tmp_zip), str(tmp_nb)],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=tmp_dir,
        )

        # Find results.json
        results_path = find_results_json(tmp_dir)
        if results_path:
            return parse_results(results_path)

        # No results.json found; report the error
        return {
            "status": "fail",
            "total_score": 0,
            "total_possible": 0,
            "per_question": {},
            "error": f"otter run did not produce results.json. "
                     f"Exit code: {result.returncode}. "
                     f"Stderr: {result.stderr[:500] if result.stderr else 'none'}",
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "fail",
            "total_score": 0,
            "total_possible": 0,
            "per_question": {},
            "error": "otter run timed out after 600 seconds",
        }
    except FileNotFoundError:
        return {
            "status": "fail",
            "total_score": 0,
            "total_possible": 0,
            "per_question": {},
            "error": "otter command not found. Install with: pip install otter-grader",
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 3:
        print("Usage: run_autograder_tests.py <notebook.ipynb> <autograder.zip>",
              file=sys.stderr)
        sys.exit(1)

    result = run(sys.argv[1], sys.argv[2])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
