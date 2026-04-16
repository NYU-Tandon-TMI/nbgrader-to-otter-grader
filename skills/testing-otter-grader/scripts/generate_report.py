#!/usr/bin/env python3
"""Aggregate testing pipeline results into a structured error report.

Input: stage log files via flags, plus student/instructor notebook paths
Output: JSON to stdout and to --output file (default: report.json)
"""

import json
import re


ISSUE_TYPE_FIX = {
    "otter_assign_syntax":       "Refactoring Agent: fix code in the identified cell",
    "otter_assign_yaml":         "Refactoring Agent: fix YAML in assignment or question config",
    "otter_assign_file_missing": "Refactoring Agent: update files: list in ASSIGNMENT CONFIG",
    "missing_autograder_dir":    "Re-run otter assign (Stage 1 may have failed silently)",
    "missing_student_dir":       "Re-run otter assign (Stage 1 may have failed silently)",
    "leaked_solution":           "Refactoring Agent: add # SOLUTION marker to solution line in instructor notebook",
    "missing_grader_check":      "Likely an otter assign bug. Flag for manual review",
    "leaked_marker":             "Refactoring Agent: malformed delimiter cell. Check raw cell type and content",
    "missing_otter_init":        "Possible otter assign bug. Verify ASSIGNMENT CONFIG is valid",
    "missing_export_cells":      "Possible otter assign bug. Verify ASSIGNMENT CONFIG has export_cell and generate settings",
    "test_failure":              "Refactoring Agent: fix solution or test code for the failing question",
    "import_error":              "Refactoring Agent: add missing dependency to files: list",
    "output_mismatch":           "Re-run instructor notebook with outputs before otter assign",
    "execution_error":           "Check notebook dependencies and cell order",
}


LEAKED_MARKERS = [
    "# SOLUTION", "# BEGIN SOLUTION", "# END SOLUTION",
    "# HIDDEN", "# BEGIN TESTS", "# END TESTS",
    "# BEGIN QUESTION", "# END QUESTION",
    "### BEGIN SOLUTION", "### END SOLUTION",
    "### BEGIN HIDDEN TESTS", "### END HIDDEN TESTS",
]


def get_cell_source(cell):
    src = cell.get("source", [])
    return "".join(src) if isinstance(src, list) else str(src)


def extract_instructor_solutions(instructor_nb_path):
    """Build a map of question name -> solution source lines from the instructor notebook."""
    try:
        with open(instructor_nb_path, "r", encoding="utf-8") as f:
            instr = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    solutions = {}
    in_solution = False
    current_q = None
    for cell in instr.get("cells", []):
        src = get_cell_source(cell)
        if cell.get("cell_type") == "raw":
            if "# BEGIN QUESTION" in src:
                for line in src.split("\n"):
                    m = re.match(r"name:\s*(q\d+)", line.strip())
                    if m:
                        current_q = m.group(1)
            elif "# BEGIN SOLUTION" in src:
                in_solution = True
            elif "# END SOLUTION" in src:
                in_solution = False
        elif in_solution and cell.get("cell_type") == "code" and current_q:
            solutions.setdefault(current_q, []).append(
                src.replace("# SOLUTION", "").strip()
            )
    return solutions


def validate_student_notebook(student_nb_path, instructor_nb_path=None):
    """Static analysis of the student notebook for structural issues."""
    issues = []

    try:
        with open(student_nb_path, "r", encoding="utf-8") as f:
            student = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return {
            "status": "fail",
            "issues": [{
                "severity": "error",
                "question": None,
                "cell_index": -1,
                "issue_type": "missing_student_dir",
                "message": f"Cannot read student notebook: {e}",
                "cell_content_snippet": "",
                "fix_action": "Verify otter assign completed successfully",
            }],
        }

    cells = student.get("cells", [])

    instructor_solutions = {}
    if instructor_nb_path:
        instructor_solutions = extract_instructor_solutions(instructor_nb_path)

    if cells:
        cell0_src = get_cell_source(cells[0])
        if "otter.Notebook" not in cell0_src and "import otter" not in cell0_src:
            issues.append({
                "severity": "error",
                "question": None,
                "cell_index": 0,
                "issue_type": "missing_otter_init",
                "message": "Cell 0 is not the otter initialization cell",
                "cell_content_snippet": cell0_src[:200],
                "fix_action": ISSUE_TYPE_FIX["missing_otter_init"],
            })

    for i, cell in enumerate(cells):
        src = get_cell_source(cell)
        for marker in LEAKED_MARKERS:
            if marker in src:
                issues.append({
                    "severity": "error",
                    "question": None,
                    "cell_index": i,
                    "issue_type": "leaked_marker",
                    "message": f"Leaked marker '{marker}' found in student notebook",
                    "cell_content_snippet": src[:200],
                    "fix_action": ISSUE_TYPE_FIX["leaked_marker"],
                })
                break

    has_check_all = False
    has_export = False
    for cell in cells[-5:]:
        src = get_cell_source(cell)
        if "grader.check_all()" in src:
            has_check_all = True
        if "grader.export(" in src:
            has_export = True

    if not has_check_all or not has_export:
        missing = []
        if not has_check_all:
            missing.append("grader.check_all()")
        if not has_export:
            missing.append("grader.export()")
        issues.append({
            "severity": "warning",
            "question": None,
            "cell_index": len(cells) - 1,
            "issue_type": "missing_export_cells",
            "message": f"Student notebook missing: {', '.join(missing)}",
            "cell_content_snippet": "",
            "fix_action": ISSUE_TYPE_FIX["missing_export_cells"],
        })

    if instructor_solutions:
        for i, cell in enumerate(cells):
            if cell.get("cell_type") != "code":
                continue
            src = get_cell_source(cell).strip()
            if not src or src == "..." or src == "…":
                continue
            for q_name, sol_lines in instructor_solutions.items():
                for sol in sol_lines:
                    if sol and sol in src and len(sol) > 10:
                        issues.append({
                            "severity": "error",
                            "question": q_name,
                            "cell_index": i,
                            "issue_type": "leaked_solution",
                            "message": f"Student cell contains solution code for {q_name}. "
                                       "The solution was not marked with # SOLUTION.",
                            "cell_content_snippet": src[:200],
                            "fix_action": ISSUE_TYPE_FIX["leaked_solution"],
                        })
                        break

    has_errors = any(iss["severity"] == "error" for iss in issues)
    status = "fail" if has_errors else "pass"
    return {"status": status, "issues": issues}


def load_json_file(path):
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def build_report(notebook_name, assign_log, structure_log, student_result,
                 autograder_log, coherence_gaps=None):
    stages = {}

    if assign_log:
        stages["otter_assign"] = {
            "status": "pass" if assign_log.get("exit_code") == 0 else "fail",
            "duration_seconds": assign_log.get("duration_seconds", 0),
            "warnings": [],
            "error_patterns": assign_log.get("error_patterns", []),
        }
        if assign_log.get("stderr"):
            stages["otter_assign"]["stderr_snippet"] = assign_log["stderr"][:500]
    else:
        stages["otter_assign"] = {"status": "skipped"}

    if structure_log:
        checks = structure_log.get("checks", [])
        stages["output_structure"] = {
            "status": structure_log.get("status", "fail"),
            "checks_passed": sum(1 for c in checks if c["status"] == "pass"),
            "checks_total": len(checks),
        }
        failed_checks = [c for c in checks if c["status"] == "fail"]
        if failed_checks:
            stages["output_structure"]["failed_checks"] = failed_checks
    else:
        stages["output_structure"] = {"status": "skipped"}

    if student_result:
        stages["student_notebook"] = student_result
    else:
        stages["student_notebook"] = {"status": "skipped", "issues": []}

    if coherence_gaps is not None:
        high = [g for g in coherence_gaps if g.get("severity") == "high"]
        stages["coherence"] = {
            "status": "advisory",
            "gaps_found": len(coherence_gaps),
            "high_severity": len(high),
            "gaps": coherence_gaps,
        }

    if autograder_log:
        stages["autograder_tests"] = {
            "status": autograder_log.get("status", "fail"),
            "total_score": autograder_log.get("total_score", 0),
            "total_possible": autograder_log.get("total_possible", 0),
            "per_question": autograder_log.get("per_question", {}),
        }
        if autograder_log.get("error"):
            stages["autograder_tests"]["error"] = autograder_log["error"]
    else:
        stages["autograder_tests"] = {"status": "skipped"}

    all_errors = []
    all_warnings = []
    failing_questions = set()

    student_issues = student_result.get("issues", []) if student_result else []
    for iss in student_issues:
        if iss["severity"] == "error":
            all_errors.append(iss)
            if iss.get("question"):
                failing_questions.add(iss["question"])
        else:
            all_warnings.append(iss)

    if autograder_log:
        for q_name, q_result in autograder_log.get("per_question", {}).items():
            if q_result.get("status") == "fail":
                failing_questions.add(q_name)
                all_errors.append({
                    "severity": "error",
                    "question": q_name,
                    "cell_index": -1,
                    "issue_type": "test_failure",
                    "message": f"Test failed for {q_name}: {q_result.get('error_type', 'unknown')}",
                    "cell_content_snippet": q_result.get("traceback", "")[:200],
                    "fix_action": ISSUE_TYPE_FIX["test_failure"],
                })

    if assign_log and assign_log.get("exit_code", 0) != 0:
        for ep in assign_log.get("error_patterns", []):
            all_errors.append({
                "severity": "error",
                "question": None,
                "cell_index": -1,
                "issue_type": ep,
                "message": f"otter assign failed: {ep}",
                "cell_content_snippet": assign_log.get("stderr", "")[:200],
                "fix_action": ISSUE_TYPE_FIX.get(ep, "Review otter assign output"),
            })

    fix_actions = []
    seen = set()
    for err in all_errors:
        q = err.get("question", "general")
        action = f"{q}: {err['fix_action']}" if q else err["fix_action"]
        if action not in seen:
            fix_actions.append(action)
            seen.add(action)

    pipeline_status = "fail" if all_errors or any(
        s.get("status") == "fail" for s in stages.values()
    ) else "pass"

    return {
        "notebook": notebook_name,
        "pipeline_status": pipeline_status,
        "stages": stages,
        "summary": {
            "total_errors": len(all_errors),
            "total_warnings": len(all_warnings),
            "failing_questions": sorted(failing_questions),
            "fix_actions": fix_actions,
        },
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate consolidated testing report")
    parser.add_argument("--notebook", required=True, help="Instructor notebook name (for report label)")
    parser.add_argument("--assign-log", default=None, help="JSON from run_otter_assign.py")
    parser.add_argument("--structure-log", default=None, help="JSON from validate_generated_output.py")
    parser.add_argument("--student-notebook", default=None, help="Path to generated student notebook")
    parser.add_argument("--instructor-notebook", default=None, help="Path to instructor notebook (for leak detection)")
    parser.add_argument("--autograder-log", default=None, help="JSON from run_autograder_tests.py")
    parser.add_argument("--coherence", default=None, help="JSON gap array from eval_student_coherence.py (advisory)")
    parser.add_argument("--output", default="report.json", help="Output report path")
    args = parser.parse_args()

    assign_log = load_json_file(args.assign_log)
    structure_log = load_json_file(args.structure_log)
    autograder_log = load_json_file(args.autograder_log)
    coherence_gaps = load_json_file(args.coherence)

    student_result = None
    if args.student_notebook:
        student_result = validate_student_notebook(
            args.student_notebook, args.instructor_notebook
        )

    report = build_report(
        args.notebook, assign_log, structure_log, student_result, autograder_log,
        coherence_gaps=coherence_gaps,
    )

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
