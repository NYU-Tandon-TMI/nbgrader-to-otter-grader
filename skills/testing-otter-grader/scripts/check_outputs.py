#!/usr/bin/env python3
"""Pre-flight check: verify instructor notebook has cell outputs before otter assign.

Usage:
    python3 scripts/check_outputs.py <notebook.ipynb>

Exit codes:
    0 — All solution cells have outputs
    1 — Some solution cells missing outputs (must execute notebook first)
"""
import json
import sys

def check_outputs(notebook_path):
    with open(notebook_path) as f:
        nb = json.load(f)

    in_solution = False
    solution_cells = []
    missing_outputs = []

    for i, cell in enumerate(nb["cells"]):
        src = "".join(cell.get("source", []))

        if cell["cell_type"] == "raw" and "BEGIN SOLUTION" in src:
            in_solution = True
            continue
        if cell["cell_type"] == "raw" and "END SOLUTION" in src:
            in_solution = False
            continue

        if in_solution and cell["cell_type"] == "code":
            has_output = bool(cell.get("outputs")) or cell.get("execution_count") is not None
            solution_cells.append(i)
            if not has_output:
                missing_outputs.append({
                    "cell_index": i,
                    "source_preview": src[:100].strip()
                })

    # Also check code cells with # SOLUTION marker (single-line solutions)
    for i, cell in enumerate(nb["cells"]):
        if cell["cell_type"] == "code" and i not in solution_cells:
            src = "".join(cell.get("source", []))
            if "# SOLUTION" in src:
                has_output = bool(cell.get("outputs")) or cell.get("execution_count") is not None
                solution_cells.append(i)
                if not has_output:
                    missing_outputs.append({
                        "cell_index": i,
                        "source_preview": src[:100].strip()
                    })

    result = {
        "notebook": notebook_path,
        "total_solution_cells": len(solution_cells),
        "cells_with_outputs": len(solution_cells) - len(missing_outputs),
        "cells_missing_outputs": len(missing_outputs),
        "missing": missing_outputs,
        "status": "pass" if not missing_outputs else "fail",
        "action": None if not missing_outputs else
            "Execute the notebook (Kernel > Restart & Run All) and save before running otter assign."
    }

    print(json.dumps(result, indent=2))
    return 0 if not missing_outputs else 1

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <notebook.ipynb>", file=sys.stderr)
        sys.exit(2)
    sys.exit(check_outputs(sys.argv[1]))
