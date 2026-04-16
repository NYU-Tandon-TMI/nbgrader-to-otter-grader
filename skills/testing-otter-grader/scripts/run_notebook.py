#!/usr/bin/env python3
"""Execute a Jupyter notebook and capture per-cell execution results.

Input: notebook path, optional --timeout (default 600s)
Output: JSON to stdout with status, cell count, and failure details.

Uses jupyter nbconvert --execute under the hood. On failure, parses the
executed notebook to identify which cells errored and extracts tracebacks.
"""

import json
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path


def parse_executed_notebook(nb_path):
    """Read an executed notebook and find cells with error outputs."""
    with open(nb_path, "r", encoding="utf-8") as f:
        nb = json.load(f)

    failures = []
    code_cell_count = 0

    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        code_cell_count += 1

        for output in cell.get("outputs", []):
            if output.get("output_type") == "error":
                traceback_lines = output.get("traceback", [])
                # Strip ANSI escape codes for readability
                import re
                clean_tb = [re.sub(r"\x1b\[[0-9;]*m", "", line) for line in traceback_lines]

                failures.append({
                    "cell_index": i,
                    "error_type": output.get("ename", "Unknown"),
                    "message": output.get("evalue", ""),
                    "traceback": "\n".join(clean_tb),
                })
                break  # One error per cell is enough

    return code_cell_count, failures


def run(notebook_path, timeout=600):
    notebook_path = Path(notebook_path).resolve()

    if not notebook_path.exists():
        return {
            "status": "fail",
            "cells_executed": 0,
            "cells_failed": 0,
            "failures": [{
                "cell_index": -1,
                "error_type": "FileNotFoundError",
                "message": f"Notebook not found: {notebook_path}",
                "traceback": "",
            }],
        }

    # Execute into a temp copy so we don't modify the original
    tmp_dir = tempfile.mkdtemp()
    tmp_nb = Path(tmp_dir) / notebook_path.name

    try:
        shutil.copy2(notebook_path, tmp_nb)

        # Copy companion files from notebook's directory to tmp so imports work
        nb_dir = notebook_path.parent
        for f in nb_dir.iterdir():
            if f.name != notebook_path.name and f.is_file():
                shutil.copy2(f, Path(tmp_dir) / f.name)
            elif f.is_dir() and f.name not in {"__pycache__", ".ipynb_checkpoints", "dist"}:
                shutil.copytree(f, Path(tmp_dir) / f.name, dirs_exist_ok=True)

        result = subprocess.run(
            [
                "jupyter", "nbconvert",
                "--to", "notebook",
                "--execute",
                "--ExecutePreprocessor.timeout=" + str(timeout),
                "--output", tmp_nb.name,
                str(tmp_nb),
            ],
            capture_output=True,
            text=True,
            timeout=timeout + 60,  # Buffer beyond cell timeout
            cwd=tmp_dir,
        )

        if result.returncode == 0:
            # Success, but still parse to count cells
            code_cells, failures = parse_executed_notebook(tmp_nb)
            return {
                "status": "pass" if not failures else "fail",
                "cells_executed": code_cells,
                "cells_failed": len(failures),
                "failures": failures,
            }
        else:
            # nbconvert failed; parse the partial output if it exists
            if tmp_nb.exists():
                code_cells, failures = parse_executed_notebook(tmp_nb)
                if failures:
                    return {
                        "status": "fail",
                        "cells_executed": code_cells,
                        "cells_failed": len(failures),
                        "failures": failures,
                    }

            # Fallback: extract what we can from stderr
            return {
                "status": "fail",
                "cells_executed": 0,
                "cells_failed": 1,
                "failures": [{
                    "cell_index": -1,
                    "error_type": "ExecutionError",
                    "message": result.stderr[:500] if result.stderr else "Unknown execution error",
                    "traceback": result.stderr or "",
                }],
            }

    except subprocess.TimeoutExpired:
        return {
            "status": "fail",
            "cells_executed": 0,
            "cells_failed": 1,
            "failures": [{
                "cell_index": -1,
                "error_type": "TimeoutError",
                "message": f"Notebook execution timed out after {timeout}s",
                "traceback": "",
            }],
        }
    except FileNotFoundError:
        return {
            "status": "fail",
            "cells_executed": 0,
            "cells_failed": 1,
            "failures": [{
                "cell_index": -1,
                "error_type": "FileNotFoundError",
                "message": "jupyter not found. Install with: pip install jupyter",
                "traceback": "",
            }],
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Execute a notebook and capture cell errors")
    parser.add_argument("notebook", help="Path to notebook")
    parser.add_argument("--timeout", type=int, default=600, help="Per-cell timeout in seconds")
    args = parser.parse_args()

    result = run(args.notebook, args.timeout)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
