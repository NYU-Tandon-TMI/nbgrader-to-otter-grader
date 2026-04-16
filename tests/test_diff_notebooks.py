import unittest
import sys
import json
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "skills" / "refactoring-nbgrader-to-otter" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).parent))

from _lib import get_source, make_raw_cell, make_code_cell
from fixtures import (
    make_notebook, make_markdown, make_code, make_raw,
    make_solution_cell, make_test_cell,
    simple_nbgrader_notebook, write_notebook, read_notebook,
)


def run_diff(original_nb, converted_nb):
    with tempfile.TemporaryDirectory() as tmp:
        orig_path = Path(tmp) / "original.ipynb"
        conv_path = Path(tmp) / "converted.ipynb"
        write_notebook(original_nb, orig_path)
        write_notebook(converted_nb, conv_path)
        from diff_notebooks import diff
        return diff(str(orig_path), str(conv_path))


def run_diff_converted_only(converted_nb):
    with tempfile.TemporaryDirectory() as tmp:
        conv_path = Path(tmp) / "converted.ipynb"
        write_notebook(converted_nb, conv_path)
        from diff_notebooks import diff_converted_only
        return diff_converted_only(str(conv_path))


class TestContentDiff(unittest.TestCase):
    def test_identical_passes(self):
        nb = simple_nbgrader_notebook()
        result = run_diff(nb, nb)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["summary"]["dropped"], 0)

    def test_dropped_cell_detected(self):
        original = simple_nbgrader_notebook()
        converted = make_notebook(original["cells"][:-1])
        result = run_diff(original, converted)
        self.assertEqual(result["status"], "fail")
        self.assertGreater(len(result["dropped_cells"]), 0)

    def test_fuzzy_match_on_modified_cell(self):
        original = make_notebook([
            make_markdown("### Question 1: This is a detailed description of the problem"),
        ])
        converted = make_notebook([
            make_markdown("### Question 1: This is a detailed description of the Problem"),
        ])
        result = run_diff(original, converted)
        self.assertEqual(result["summary"]["dropped"], 0)

    def test_short_cell_exact_match_only(self):
        original = make_notebook([make_markdown("# HW1"), make_markdown("# HW1")])
        converted = make_notebook([make_markdown("# HW1")])
        result = run_diff(original, converted)
        self.assertEqual(result["summary"]["dropped"], 1)

    def test_solution_and_test_cells_excluded(self):
        original = simple_nbgrader_notebook()
        converted = make_notebook([c for c in original["cells"] if c["cell_type"] == "markdown"])
        result = run_diff(original, converted)
        self.assertEqual(result["summary"]["dropped"], 0)


class TestStructuralGap(unittest.TestCase):
    def test_code_between_questions_flagged(self):
        converted = make_notebook([
            make_raw("# BEGIN QUESTION\nname: q1\npoints: 1"),
            make_raw("# BEGIN SOLUTION"),
            make_code("q1 = 1 # SOLUTION"),
            make_raw("# END SOLUTION"),
            make_raw("# END QUESTION"),
            make_code("orphan_code = True"),
            make_raw("# BEGIN QUESTION\nname: q2\npoints: 1"),
            make_raw("# BEGIN SOLUTION"),
            make_code("q2 = 2 # SOLUTION"),
            make_raw("# END SOLUTION"),
            make_raw("# END QUESTION"),
        ])
        result = run_diff_converted_only(converted)
        self.assertGreater(len(result["misplaced_cells"]), 0)

    def test_markdown_between_questions_not_flagged(self):
        converted = make_notebook([
            make_raw("# BEGIN QUESTION\nname: q1\npoints: 1"),
            make_raw("# BEGIN SOLUTION"),
            make_code("q1 = 1 # SOLUTION"),
            make_raw("# END SOLUTION"),
            make_raw("# END QUESTION"),
            make_markdown("### Question 2"),
            make_raw("# BEGIN QUESTION\nname: q2\npoints: 1"),
            make_raw("# BEGIN SOLUTION"),
            make_code("q2 = 2 # SOLUTION"),
            make_raw("# END SOLUTION"),
            make_raw("# END QUESTION"),
        ])
        result = run_diff_converted_only(converted)
        misplaced_code = [m for m in result["misplaced_cells"] if m["cell_type"] == "code"]
        self.assertEqual(len(misplaced_code), 0)

    def test_grade_only_cell_between_questions_not_flagged(self):
        converted = make_notebook([
            make_raw("# BEGIN QUESTION\nname: q1\npoints: 1"),
            make_raw("# BEGIN SOLUTION"),
            make_code("q1 = 1 # SOLUTION"),
            make_raw("# END SOLUTION"),
            make_raw("# END QUESTION"),
            make_test_cell("assert q1 == 1", points=1),
            make_raw("# BEGIN QUESTION\nname: q2\npoints: 1"),
            make_raw("# BEGIN SOLUTION"),
            make_code("q2 = 2 # SOLUTION"),
            make_raw("# END SOLUTION"),
            make_raw("# END QUESTION"),
        ])
        result = run_diff_converted_only(converted)
        self.assertEqual(len(result["misplaced_cells"]), 0)

    def test_code_before_first_question_not_flagged(self):
        converted = make_notebook([
            make_raw("# ASSIGNMENT CONFIG\nname: hw1"),
            make_code("import numpy as np"),
            make_raw("# BEGIN QUESTION\nname: q1\npoints: 1"),
            make_raw("# BEGIN SOLUTION"),
            make_code("q1 = 1 # SOLUTION"),
            make_raw("# END SOLUTION"),
            make_raw("# END QUESTION"),
        ])
        result = run_diff_converted_only(converted)
        misplaced_code = [m for m in result["misplaced_cells"] if m["cell_type"] == "code"]
        self.assertEqual(len(misplaced_code), 0)


if __name__ == "__main__":
    unittest.main()
