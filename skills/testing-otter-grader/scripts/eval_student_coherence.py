#!/usr/bin/env python3
"""Extract student-facing cells and print an LLM coherence evaluation prompt.

Input: path to a student notebook
Output: evaluation prompt to stdout, or a pass-result JSON if no content cells found.
"""

import json
import sys


SKIP_PATTERNS = ("...", "grader.check", "grader.export")


def extract_student_content(notebook_path):
    with open(notebook_path, "r", encoding="utf-8") as f:
        nb = json.load(f)

    content_cells = []
    for i, cell in enumerate(nb["cells"]):
        cell_type = cell.get("cell_type", "")
        src = cell.get("source", "")
        if isinstance(src, list):
            src = "".join(src)
        if not src.strip():
            continue

        if cell_type == "markdown":
            content_cells.append({"index": i, "type": "markdown", "source": src})
        elif cell_type == "code":
            if "# YOUR CODE HERE" in src.upper():
                continue
            if any(p in src for p in SKIP_PATTERNS):
                continue
            content_cells.append({"index": i, "type": "code", "source": src})

    return content_cells


def build_eval_prompt(content_cells):
    sections = [
        f"[Cell {c['index']}] ({c['type']})\n{c['source']}"
        for c in content_cells
    ]
    cells_text = "\n\n---\n\n".join(sections)

    return f"""You are a student reading this Jupyter notebook assignment for the first time.
Read each cell in order. For each gap you find, report it as a JSON object.

A "gap" is any place where:
(a) A term, variable, or concept is referenced but never introduced earlier in the notebook
(b) An instruction references a previous step that does not exist
(c) The flow between two consecutive instruction cells has a missing piece — context needed to understand the current cell was never provided

Report ONLY genuine gaps that would confuse a student. Do NOT flag:
- Standard Python/library imports (students know these)
- Variables that students are asked to create (solution placeholders)
- References to external datasets (these are provided separately)

Output a JSON array of objects, each with:
- "cell_index": the cell number where the gap appears
- "description": what is missing or incoherent
- "severity": "high" (blocks understanding) or "medium" (causes confusion)

If there are no gaps, output an empty array: []

--- NOTEBOOK CONTENT ---

{cells_text}"""


def main():
    import argparse
    parser = argparse.ArgumentParser(description="LLM-as-student coherence evaluation")
    parser.add_argument("notebook", help="Path to student notebook")
    args = parser.parse_args()

    content = extract_student_content(args.notebook)

    if not content:
        result = {"status": "pass", "gaps": [], "summary": {"total_cells": 0, "gaps_found": 0}}
        print(json.dumps(result, indent=2))
        sys.exit(0)

    prompt = build_eval_prompt(content)

    print(prompt)


if __name__ == "__main__":
    main()
