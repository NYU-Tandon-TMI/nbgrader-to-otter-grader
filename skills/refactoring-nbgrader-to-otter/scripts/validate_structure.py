#!/usr/bin/env python3
"""Validate the structural integrity of an otter-grader instructor notebook.

Checks 6 categories:
1. Assignment Config (cell 0)
2. Delimiter Integrity (matched BEGIN/END, raw cells, nesting)
3. Question Config (valid YAML, sequential names, non-negative points)
4. Solution Markers (# SOLUTION present in solution blocks)
5. Test Structure (code cells in test blocks, # HIDDEN format)
6. Cleanup Verification (no orphaned nbgrader markers or placeholders)

Input: path to transformed notebook, --cwd path for file existence checks
Output: JSON to stdout with status, errors, warnings, summary
Exit code: 0 if pass, 1 if fail
"""

import json
import re
import sys
import argparse
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_source(cell):
    """Get cell source as a single string."""
    src = cell.get("source", [])
    if isinstance(src, list):
        return "".join(src)
    return src or ""


def cell_type(cell):
    return cell.get("cell_type", "")


# ---------------------------------------------------------------------------
# Category 1: Assignment Config
# ---------------------------------------------------------------------------

def check_assignment_config(cells, cwd):
    errors = []
    warnings = []

    if not cells:
        errors.append({"category": "assignment_config", "cell_index": 0,
                        "message": "Notebook has no cells"})
        return errors, warnings

    cell0 = cells[0]
    src = get_source(cell0)

    if cell_type(cell0) != "raw":
        errors.append({"category": "assignment_config", "cell_index": 0,
                        "message": f"Cell 0 is {cell_type(cell0)}, must be raw"})
        return errors, warnings

    if not src.strip().startswith("# ASSIGNMENT CONFIG"):
        errors.append({"category": "assignment_config", "cell_index": 0,
                        "message": "Cell 0 does not start with '# ASSIGNMENT CONFIG'"})
        return errors, warnings

    # Parse YAML (skip the header line)
    yaml_text = "\n".join(src.strip().split("\n")[1:])
    config = None

    if HAS_YAML:
        try:
            config = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            errors.append({"category": "assignment_config", "cell_index": 0,
                            "message": f"Invalid YAML: {e}"})
            return errors, warnings
    else:
        # Minimal parse without pyyaml
        config = _minimal_yaml_parse(yaml_text)
        if config is None:
            warnings.append({"category": "assignment_config", "cell_index": 0,
                              "message": "pyyaml not installed; YAML validation skipped"})
            return errors, warnings

    if not isinstance(config, dict):
        errors.append({"category": "assignment_config", "cell_index": 0,
                        "message": "Assignment config YAML is not a dictionary"})
        return errors, warnings

    # Required keys
    for key in ("name", "environment", "files", "generate"):
        if key not in config:
            errors.append({"category": "assignment_config", "cell_index": 0,
                            "message": f"Missing required key: {key}"})

    if config.get("environment") != "environment.yml":
        warnings.append({"category": "assignment_config", "cell_index": 0,
                          "message": f"environment is '{config.get('environment')}', expected 'environment.yml'"})

    # Check files exist in CWD
    files_list = config.get("files", [])
    if isinstance(files_list, list):
        if cwd and (Path(cwd) / "utils.py").exists() and "utils.py" not in files_list:
            errors.append({"category": "assignment_config", "cell_index": 0,
                            "message": "utils.py exists in CWD but not listed in files:"})
        if cwd:
            for fname in files_list:
                fpath = Path(cwd) / fname
                if not fpath.exists():
                    errors.append({"category": "assignment_config", "cell_index": 0,
                                    "message": f"File '{fname}' listed in files: but not found in CWD"})

    return errors, warnings


def _minimal_yaml_parse(text):
    """Fallback parser: extract top-level keys from simple YAML."""
    result = {}
    for line in text.split("\n"):
        m = re.match(r"^(\w[\w-]*):\s*(.*)", line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            if val.lower() == "false":
                result[key] = False
            elif val.lower() == "true":
                result[key] = True
            elif val == "":
                result[key] = None
            else:
                result[key] = val
    # Try to extract files: list
    if "files" in result and result["files"] is None:
        files = []
        in_files = False
        for line in text.split("\n"):
            if re.match(r"^files:\s*$", line):
                in_files = True
                continue
            if in_files:
                m = re.match(r"^\s+-\s+(.+)", line)
                if m:
                    files.append(m.group(1).strip())
                elif line.strip() and not line.startswith(" "):
                    break
        result["files"] = files
    return result


# ---------------------------------------------------------------------------
# Category 2: Delimiter Integrity
# ---------------------------------------------------------------------------

DELIMITER_PATTERNS = {
    "# BEGIN QUESTION": "begin_question",
    "# END QUESTION": "end_question",
    "# BEGIN SOLUTION": "begin_solution",
    "# END SOLUTION": "end_solution",
    "# BEGIN TESTS": "begin_tests",
    "# END TESTS": "end_tests",
}


def identify_delimiter(src):
    """Return delimiter type if the cell source starts with a known delimiter, else None."""
    first_line = src.strip().split("\n")[0].strip() if src.strip() else ""
    for pattern, dtype in DELIMITER_PATTERNS.items():
        if first_line == pattern or first_line.startswith(pattern):
            # Distinguish: "# BEGIN QUESTION" vs "# BEGIN SOLUTION" when line starts with "# BEGIN"
            if first_line == pattern or first_line.startswith(pattern + "\n") or first_line.startswith(pattern + " "):
                return dtype
            # Exact match on the full first line
            if first_line.rstrip() == pattern:
                return dtype
    return None


def check_delimiters(cells):
    errors = []
    warnings = []

    # Collect all delimiter cells
    delimiters = []
    for i, cell in enumerate(cells):
        src = get_source(cell)
        dtype = identify_delimiter(src)
        if dtype:
            delimiters.append((i, dtype, cell_type(cell)))

    # All delimiter cells must be raw
    for idx, dtype, ctype in delimiters:
        if ctype != "raw":
            errors.append({"category": "delimiter_integrity", "cell_index": idx,
                            "message": f"{dtype} is a {ctype} cell, must be raw"})

    # Check matching pairs
    pairs = [
        ("begin_question", "end_question", "QUESTION"),
        ("begin_solution", "end_solution", "SOLUTION"),
        ("begin_tests", "end_tests", "TESTS"),
    ]

    for begin_type, end_type, label in pairs:
        begins = [(i, d) for i, d, _ in delimiters if d == begin_type]
        ends = [(i, d) for i, d, _ in delimiters if d == end_type]

        if len(begins) != len(ends):
            errors.append({"category": "delimiter_integrity", "cell_index": -1,
                            "message": f"Mismatched {label}: {len(begins)} BEGIN vs {len(ends)} END"})

    # Check nesting: SOLUTION and TESTS must be inside QUESTION blocks
    stack = []
    question_ranges = []
    solution_ranges = []
    test_ranges = []

    for idx, dtype, _ in delimiters:
        if dtype == "begin_question":
            stack.append(("question", idx))
        elif dtype == "end_question":
            if stack and stack[-1][0] == "question":
                begin_idx = stack.pop()[1]
                question_ranges.append((begin_idx, idx))
            else:
                errors.append({"category": "delimiter_integrity", "cell_index": idx,
                                "message": "END QUESTION without matching BEGIN QUESTION"})
        elif dtype == "begin_solution":
            stack.append(("solution", idx))
        elif dtype == "end_solution":
            if stack and stack[-1][0] == "solution":
                begin_idx = stack.pop()[1]
                solution_ranges.append((begin_idx, idx))
            else:
                errors.append({"category": "delimiter_integrity", "cell_index": idx,
                                "message": "END SOLUTION without matching BEGIN SOLUTION"})
        elif dtype == "begin_tests":
            stack.append(("tests", idx))
        elif dtype == "end_tests":
            if stack and stack[-1][0] == "tests":
                begin_idx = stack.pop()[1]
                test_ranges.append((begin_idx, idx))
            else:
                errors.append({"category": "delimiter_integrity", "cell_index": idx,
                                "message": "END TESTS without matching BEGIN TESTS"})

    # Check SOLUTION and TESTS are inside QUESTION
    for s_begin, s_end in solution_ranges:
        inside = any(q_begin < s_begin and s_end < q_end for q_begin, q_end in question_ranges)
        if not inside:
            errors.append({"category": "delimiter_integrity", "cell_index": s_begin,
                            "message": "SOLUTION block is not inside a QUESTION block"})

    for t_begin, t_end in test_ranges:
        inside = any(q_begin < t_begin and t_end < q_end for q_begin, q_end in question_ranges)
        if not inside:
            errors.append({"category": "delimiter_integrity", "cell_index": t_begin,
                            "message": "TESTS block is not inside a QUESTION block"})

    # Check SOLUTION appears before TESTS within each QUESTION
    for q_begin, q_end in question_ranges:
        q_solutions = [(s, e) for s, e in solution_ranges if q_begin < s and e < q_end]
        q_tests = [(s, e) for s, e in test_ranges if q_begin < s and e < q_end]
        if q_solutions and q_tests:
            last_sol_end = max(e for _, e in q_solutions)
            first_test_begin = min(s for s, _ in q_tests)
            if last_sol_end > first_test_begin:
                errors.append({"category": "delimiter_integrity", "cell_index": q_begin,
                                "message": "SOLUTION appears after TESTS in QUESTION block"})

    return errors, warnings, question_ranges, solution_ranges, test_ranges


# ---------------------------------------------------------------------------
# Category 3: Question Config
# ---------------------------------------------------------------------------

def check_question_configs(cells, question_ranges):
    errors = []
    warnings = []
    question_names = []

    for q_begin, q_end in question_ranges:
        src = get_source(cells[q_begin])
        # Parse YAML from BEGIN QUESTION cell (skip the header line)
        lines = src.strip().split("\n")
        yaml_lines = [l for l in lines[1:] if l.strip()]
        yaml_text = "\n".join(yaml_lines)

        config = None
        if HAS_YAML:
            try:
                config = yaml.safe_load(yaml_text)
            except yaml.YAMLError as e:
                errors.append({"category": "question_config", "cell_index": q_begin,
                                "message": f"Invalid YAML in BEGIN QUESTION: {e}"})
                continue
        else:
            config = {}
            for line in yaml_lines:
                m = re.match(r"^(\w+):\s*(.+)", line)
                if m:
                    key = m.group(1)
                    val = m.group(2).strip()
                    config[key] = val

        if not isinstance(config, dict):
            errors.append({"category": "question_config", "cell_index": q_begin,
                            "message": "Question config is not a dictionary"})
            continue

        if "name" not in config:
            errors.append({"category": "question_config", "cell_index": q_begin,
                            "message": "Missing 'name' in question config"})
        else:
            question_names.append((config["name"], q_begin))

        if "points" not in config:
            errors.append({"category": "question_config", "cell_index": q_begin,
                            "message": "Missing 'points' in question config"})
        else:
            try:
                pts = int(config["points"])
                if pts < 0:
                    errors.append({"category": "question_config", "cell_index": q_begin,
                                    "message": f"Negative points: {pts}"})
                elif pts == 0:
                    warnings.append({"category": "question_config", "cell_index": q_begin,
                                      "message": f"Question {config.get('name', '?')} has 0 points"})
            except (TypeError, ValueError):
                errors.append({"category": "question_config", "cell_index": q_begin,
                                "message": f"Points is not an integer: {config['points']}"})

    # Check sequential naming: q1, q2, ..., qN
    q_names_seen = []
    for name, idx in question_names:
        m = re.match(r"^q(\d+)(_\d+)*$", str(name))
        if m:
            q_names_seen.append((str(name), idx))
        else:
            warnings.append({"category": "question_config", "cell_index": idx,
                              "message": f"Question name '{name}' does not follow qN pattern"})

    if q_names_seen:
        seen = set()
        for qname, idx in q_names_seen:
            if qname in seen:
                errors.append({"category": "question_config", "cell_index": idx,
                                "message": f"Duplicate question name: {qname}"})
            seen.add(qname)

    return errors, warnings


# ---------------------------------------------------------------------------
# Category 4: Solution Markers
# ---------------------------------------------------------------------------

def check_solution_markers(cells, solution_ranges):
    errors = []
    warnings = []

    for s_begin, s_end in solution_ranges:
        code_cells_in_block = []
        for i in range(s_begin + 1, s_end):
            if cell_type(cells[i]) == "code":
                code_cells_in_block.append(i)

        if not code_cells_in_block:
            errors.append({"category": "solution_markers", "cell_index": s_begin,
                            "message": "SOLUTION block contains no code cells"})
            continue

        for ci in code_cells_in_block:
            src = get_source(cells[ci])
            has_inline = "# SOLUTION" in src
            has_block_begin = "# BEGIN SOLUTION" in src
            has_block_end = "# END SOLUTION" in src
            has_block = has_block_begin and has_block_end

            if not has_inline and not has_block:
                errors.append({"category": "solution_markers", "cell_index": ci,
                                "message": "Code cell in SOLUTION block has no # SOLUTION marker or # BEGIN SOLUTION / # END SOLUTION wrapper"})

    # Check no # SOLUTION markers outside solution blocks
    solution_cell_indices = set()
    for s_begin, s_end in solution_ranges:
        for i in range(s_begin, s_end + 1):
            solution_cell_indices.add(i)

    for i, cell in enumerate(cells):
        if i in solution_cell_indices:
            continue
        if cell_type(cell) != "code":
            continue
        src = get_source(cell)
        if "# SOLUTION" in src:
            errors.append({"category": "solution_markers", "cell_index": i,
                            "message": "# SOLUTION marker found outside SOLUTION block"})

    return errors, warnings


# ---------------------------------------------------------------------------
# Category 5: Test Structure
# ---------------------------------------------------------------------------

def check_test_structure(cells, test_ranges):
    errors = []
    warnings = []

    for t_begin, t_end in test_ranges:
        code_cells_in_block = []
        for i in range(t_begin + 1, t_end):
            if cell_type(cells[i]) == "code":
                code_cells_in_block.append(i)

        if not code_cells_in_block:
            errors.append({"category": "test_structure", "cell_index": t_begin,
                            "message": "TESTS block contains no code cells"})
            continue

        for ci in code_cells_in_block:
            src = get_source(cells[ci])
            lines = src.strip().split("\n")
            first_line = lines[0].strip() if lines else ""

            # Check # HIDDEN format
            if "HIDDEN" in first_line.upper():
                if first_line != "# HIDDEN":
                    errors.append({"category": "test_structure", "cell_index": ci,
                                    "message": f"HIDDEN marker format wrong: '{first_line}', must be exactly '# HIDDEN'"})

    return errors, warnings


# ---------------------------------------------------------------------------
# Category 6: Cleanup Verification
# ---------------------------------------------------------------------------

ORPHANED_PATTERNS = [
    (re.compile(r"###?\s*BEGIN\s+SOLUTION\s*#*", re.IGNORECASE), "### BEGIN SOLUTION"),
    (re.compile(r"###?\s*END\s+SOLUTION\s*#*", re.IGNORECASE), "### END SOLUTION"),
    (re.compile(r"###?\s*BEGIN\s+HIDDEN\s+TESTS\s*#*", re.IGNORECASE), "### BEGIN HIDDEN TESTS"),
    (re.compile(r"###?\s*END\s+HIDDEN\s+TESTS\s*#*", re.IGNORECASE), "### END HIDDEN TESTS"),
    (re.compile(r"^\s*#\s*TEST\s*$", re.IGNORECASE), "# TEST"),
    (re.compile(r"^\s*#TEST\s*$", re.IGNORECASE), "#TEST"),
]

PLACEHOLDER_ARTIFACT_RE = re.compile(r"^\s*\w[\w\s]*=\s*\.\.\.\s*$")
BARE_ELLIPSIS_ARTIFACT_RE = re.compile(r"^\s*(\.\.\.|…)\s*$")


def check_cleanup(cells, solution_ranges):
    errors = []
    warnings = []

    # Build set of raw delimiter cell indices to skip (they legitimately contain "# BEGIN SOLUTION" etc.)
    delimiter_indices = set()
    for s_begin, s_end in solution_ranges:
        delimiter_indices.add(s_begin)
        delimiter_indices.add(s_end)

    for i, cell in enumerate(cells):
        if i == 0:  # skip assignment config
            continue
        src = get_source(cell)
        ct = cell_type(cell)

        # Only check code cells for orphaned markers (raw delimiter cells are expected)
        if ct == "code":
            for line in src.split("\n"):
                stripped = line.strip()
                for pattern, label in ORPHANED_PATTERNS:
                    if pattern.match(stripped):
                        errors.append({"category": "cleanup", "cell_index": i,
                                        "message": f"Orphaned nbgrader marker: {label}"})

                # Check placeholder artifacts
                if PLACEHOLDER_ARTIFACT_RE.match(stripped):
                    # Avoid false positive on legit code like `x = ...` in type hints
                    errors.append({"category": "cleanup", "cell_index": i,
                                    "message": f"Placeholder artifact: {stripped}"})

                if BARE_ELLIPSIS_ARTIFACT_RE.match(stripped):
                    errors.append({"category": "cleanup", "cell_index": i,
                                    "message": "Bare ellipsis placeholder found"})

        # Check for lingering nbgrader metadata — otter-grader does not use
        # metadata, so ALL nbgrader metadata must be removed after analysis.
        meta = cell.get("metadata", {}).get("nbgrader", None)
        if meta is not None:
            errors.append({"category": "cleanup", "cell_index": i,
                           "message": "Cell still has nbgrader metadata. Remove cell.metadata.nbgrader entirely."})

    return errors, warnings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def validate(notebook_path, cwd=None, skip_cleanup=False):
    with open(notebook_path, "r", encoding="utf-8") as f:
        nb = json.load(f)

    cells = nb.get("cells", [])
    all_errors = []
    all_warnings = []

    # Category 1
    e, w = check_assignment_config(cells, cwd)
    all_errors.extend(e)
    all_warnings.extend(w)

    # Category 2
    e, w, question_ranges, solution_ranges, test_ranges = check_delimiters(cells)
    all_errors.extend(e)
    all_warnings.extend(w)

    # Category 3
    e, w = check_question_configs(cells, question_ranges)
    all_errors.extend(e)
    all_warnings.extend(w)

    # Category 4
    e, w = check_solution_markers(cells, solution_ranges)
    all_errors.extend(e)
    all_warnings.extend(w)

    # Category 5
    e, w = check_test_structure(cells, test_ranges)
    all_errors.extend(e)
    all_warnings.extend(w)

    # Category 6
    if not skip_cleanup:
        e, w = check_cleanup(cells, solution_ranges)
        all_errors.extend(e)
        all_warnings.extend(w)

    status = "fail" if all_errors else "pass"
    result = {
        "status": status,
        "errors": all_errors,
        "warnings": all_warnings,
        "summary": {
            "questions_found": len(question_ranges),
            "errors": len(all_errors),
            "warnings": len(all_warnings),
        },
    }

    print(json.dumps(result, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate otter-grader instructor notebook structure")
    parser.add_argument("notebook", help="Path to the instructor notebook")
    parser.add_argument("--cwd", default=None, help="Working directory for file existence checks")
    parser.add_argument("--skip-cleanup", action="store_true",
                        help="Skip Category 6 (cleanup verification). Use during eval loop before metadata strip.")
    args = parser.parse_args()

    cwd = args.cwd or str(Path(args.notebook).parent)
    exit_code = validate(args.notebook, cwd, skip_cleanup=args.skip_cleanup)
    sys.exit(exit_code)
