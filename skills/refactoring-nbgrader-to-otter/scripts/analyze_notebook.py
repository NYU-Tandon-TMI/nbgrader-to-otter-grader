#!/usr/bin/env python3
"""Analyze an nbgrader notebook and produce a JSON question map.

Input: path to nbgrader notebook
Output: JSON to stdout with assignment name, questions array, and companion files.

Each question includes cell indices, points, solution type, and recommended approach.
The recommended_approach is advisory, not mandatory. The agent may override to
llm_assisted if the deterministic transform fails or the Testing Agent reports errors.
"""

import json
import re
import sys
import ast
from pathlib import Path


# ---------------------------------------------------------------------------
# NBGrader metadata helpers
# ---------------------------------------------------------------------------

def get_nbgrader_meta(cell):
    """Return the nbgrader metadata dict, or empty dict if absent."""
    return cell.get("metadata", {}).get("nbgrader", {})


def is_solution_cell(cell):
    return bool(get_nbgrader_meta(cell).get("solution", False))


def is_test_cell(cell):
    return bool(get_nbgrader_meta(cell).get("grade", False))


def get_points(cell, default=0):
    meta = get_nbgrader_meta(cell)
    try:
        p = int(meta.get("points", default))
        return p if p >= 0 else default
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Question name extraction
# ---------------------------------------------------------------------------

QUESTION_HEADER_RE = re.compile(
    r"###?\s*Question\s+(\d+)", re.IGNORECASE
)


def extract_question_number(cells, before_index):
    """Walk backwards from before_index to find the nearest ### Question N header."""
    for i in range(before_index - 1, -1, -1):
        cell = cells[i]
        if cell.get("cell_type") != "markdown":
            continue
        src = "".join(cell.get("source", []))
        m = QUESTION_HEADER_RE.search(src)
        if m:
            return int(m.group(1)), i
    return None, None


# ---------------------------------------------------------------------------
# Solution complexity classification
# ---------------------------------------------------------------------------

# Patterns for nbgrader markers to strip before analysis
NBGRADER_MARKERS = [
    re.compile(r"^\s*###?\s*BEGIN\s+SOLUTION\s*#*\s*$", re.IGNORECASE),
    re.compile(r"^\s*###?\s*END\s+SOLUTION\s*#*\s*$", re.IGNORECASE),
    re.compile(r"^\s*###?\s*BEGIN\s+HIDDEN\s+TESTS\s*#*\s*$", re.IGNORECASE),
    re.compile(r"^\s*###?\s*END\s+HIDDEN\s+TESTS\s*#*\s*$", re.IGNORECASE),
]

PLACEHOLDER_RE = re.compile(r"^\s*\w[\w\s]*=\s*\.\.\.(\s*)$")
BARE_ELLIPSIS_RE = re.compile(r"^\s*(\.\.\.|…)\s*$")


def strip_nbgrader_artifacts(source):
    """Remove nbgrader markers and placeholder lines, return cleaned lines."""
    lines = source.split("\n")
    cleaned = []
    for line in lines:
        if any(p.match(line) for p in NBGRADER_MARKERS):
            continue
        if PLACEHOLDER_RE.match(line):
            continue
        if BARE_ELLIPSIS_RE.match(line):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def classify_solution(source):
    """Classify solution as 'simple' or 'complex' after stripping nbgrader artifacts.

    Simple: single variable assignment to a literal value.
    Complex: everything else.
    """
    cleaned = strip_nbgrader_artifacts(source)
    if not cleaned:
        return "simple"  # empty solution, treat as simple

    lines = [l for l in cleaned.split("\n") if l.strip()]
    if len(lines) != 1:
        return "complex"

    line = lines[0].strip()
    # Must match: identifier = literal
    m = re.match(r"^(\w+)\s*=\s*(.+)$", line)
    if not m:
        return "complex"

    value_str = m.group(2).strip()
    try:
        node = ast.parse(value_str, mode="eval").body
        if is_literal_node(node):
            return "simple"
    except SyntaxError:
        pass

    return "complex"


def is_literal_node(node):
    """Check if an AST node is a simple literal (str, num, bool, None, tuple, list of literals)."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Tuple, ast.List)):
        return all(is_literal_node(elt) for elt in node.elts)
    if isinstance(node, ast.Set):
        return all(is_literal_node(elt) for elt in node.elts)
    # Handle negative numbers: UnaryOp(USub, Constant)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return isinstance(node.operand, ast.Constant)
    return False


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def analyze_notebook(notebook_path):
    nb_path = Path(notebook_path)
    with open(nb_path, "r", encoding="utf-8") as f:
        nb = json.load(f)

    cells = nb.get("cells", [])
    assignment_name = nb_path.stem

    # Build question groups: group consecutive solution+test cells into questions
    questions = []
    auto_counter = 1
    i = 0

    while i < len(cells):
        cell = cells[i]

        if is_solution_cell(cell):
            # Found start of a question. Collect all solution cells.
            solution_cells = [i]
            i += 1

            # Collect additional solution cells (may have non-solution cells between)
            while i < len(cells):
                if is_solution_cell(cells[i]):
                    solution_cells.append(i)
                    i += 1
                elif is_test_cell(cells[i]):
                    break  # tests found, stop collecting solutions
                elif cells[i].get("cell_type") in ("markdown", "code"):
                    # Non-functional cell between solutions: peek ahead for more solutions
                    j = i + 1
                    while j < len(cells) and not is_solution_cell(cells[j]) and not is_test_cell(cells[j]):
                        j += 1
                    if j < len(cells) and is_solution_cell(cells[j]):
                        i += 1  # skip non-functional, continue collecting
                    else:
                        break  # no more solutions ahead
                else:
                    break

            # Collect test cells
            test_cells = []
            while i < len(cells) and not is_solution_cell(cells[i]):
                if is_test_cell(cells[i]):
                    test_cells.append(i)
                i += 1

            # Extract question number from nearest preceding markdown header
            q_num, header_idx = extract_question_number(cells, solution_cells[0])
            if q_num is not None:
                q_name = f"q{q_num}"
            else:
                q_name = f"q{auto_counter}"
            auto_counter = (q_num or auto_counter) + 1

            # Sum points from test cells
            total_points = sum(get_points(cells[ti], default=0) for ti in test_cells)
            # If no test cells but we have solution, points = 0
            if not test_cells:
                total_points = 0

            # Classify solution complexity
            all_solution_src = "\n".join(
                "".join(cells[si].get("source", [])) for si in solution_cells
            )
            sol_type = classify_solution(all_solution_src)

            # For multi-solution-cell questions, always recommend llm_assisted
            if len(solution_cells) > 1:
                recommended = "llm_assisted"
                sol_type = "complex"
            else:
                recommended = "deterministic" if sol_type == "simple" else "llm_assisted"

            questions.append({
                "name": q_name,
                "header_cell_index": header_idx,
                "solution_cells": solution_cells,
                "test_cells": test_cells,
                "points": total_points,
                "solution_type": sol_type,
                "recommended_approach": recommended,
            })
            continue

        # Standalone test cell without preceding solution (edge case)
        if is_test_cell(cell):
            test_cells = [i]
            i += 1
            while i < len(cells) and is_test_cell(cells[i]):
                test_cells.append(i)
                i += 1

            q_num, header_idx = extract_question_number(cells, test_cells[0])
            if q_num is not None:
                q_name = f"q{q_num}"
            else:
                q_name = f"q{auto_counter}"
            auto_counter = (q_num or auto_counter) + 1

            total_points = sum(get_points(cells[ti], default=0) for ti in test_cells)

            questions.append({
                "name": q_name,
                "header_cell_index": header_idx,
                "solution_cells": [],
                "test_cells": test_cells,
                "points": total_points,
                "solution_type": "none",
                "recommended_approach": "deterministic",
            })
            continue

        i += 1

    # Detect companion files in CWD
    cwd = nb_path.parent
    data_extensions = {".csv", ".json", ".txt", ".md", ".tsv", ".yml", ".yaml"}
    companion_files = []
    for f in sorted(cwd.iterdir()):
        if f.is_file() and f.name != nb_path.name and f.suffix != ".ipynb":
            if f.suffix in data_extensions or f.name in ("utils.py", "environment.yml"):
                companion_files.append(f.name)

    result = {
        "assignment_name": assignment_name,
        "questions": questions,
        "companion_files": companion_files,
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <notebook.ipynb>", file=sys.stderr)
        sys.exit(1)
    analyze_notebook(sys.argv[1])
