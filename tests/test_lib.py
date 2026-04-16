import unittest
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "skills" / "refactoring-nbgrader-to-otter" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from _lib import (
    get_source, is_solution_cell, is_test_cell, get_points,
    find_question_header, is_inside_question_block,
    strip_solution_markers, split_test_content,
    make_raw_cell, make_code_cell, identify_delimiter,
    is_otter_infrastructure, find_question_blocks,
)
from fixtures import (
    make_markdown, make_code, make_raw, make_solution_cell,
    make_test_cell, make_notebook,
)


class TestNbgraderDetection(unittest.TestCase):
    def test_is_solution_cell(self):
        self.assertTrue(is_solution_cell(make_solution_cell("x = 1")))
        self.assertFalse(is_solution_cell(make_code("x = 1")))
        self.assertFalse(is_solution_cell(make_markdown("text")))

    def test_is_test_cell(self):
        self.assertTrue(is_test_cell(make_test_cell("assert True")))
        self.assertFalse(is_test_cell(make_code("x = 1")))

    def test_get_points(self):
        self.assertEqual(get_points(make_test_cell("assert True", points=3)), 3)
        self.assertEqual(get_points(make_code("x = 1")), 0)


class TestQuestionDiscovery(unittest.TestCase):
    def test_find_header(self):
        cells = [
            make_markdown("# Homework"),
            make_markdown("### Question 3: Compute"),
            make_solution_cell("q3 = 1"),
        ]
        num, idx = find_question_header(cells, 2)
        self.assertEqual(num, 3)
        self.assertEqual(idx, 1)

    def test_no_header(self):
        cells = [make_code("setup"), make_solution_cell("q1 = 1")]
        num, idx = find_question_header(cells, 1)
        self.assertIsNone(num)
        self.assertIsNone(idx)

    def test_find_header_beyond_15_cells(self):
        cells = [make_markdown("### Question 7: Deep")] + [make_markdown(f"Instruction {i}") for i in range(20)] + [make_solution_cell("q7 = 1")]
        num, idx = find_question_header(cells, len(cells) - 1)
        self.assertEqual(num, 7)
        self.assertEqual(idx, 0)

    def test_inside_question_block(self):
        cells = [
            make_raw("# BEGIN QUESTION\nname: q1\npoints: 1"),
            make_code("inside"),
            make_raw("# END QUESTION"),
            make_code("outside"),
        ]
        self.assertTrue(is_inside_question_block(cells, 1))
        self.assertFalse(is_inside_question_block(cells, 3))


class TestMarkerStripping(unittest.TestCase):
    def test_strip_solution(self):
        source = "q1 = ...\n### BEGIN SOLUTION ###\nq1 = 42\n### END SOLUTION ###"
        result = strip_solution_markers(source)
        self.assertEqual(result, "q1 = 42")

    def test_strip_bare_ellipsis(self):
        source = "...\n### BEGIN SOLUTION ###\nresult = 5\n### END SOLUTION ###"
        result = strip_solution_markers(source)
        self.assertEqual(result, "result = 5")


class TestSplitTestContent(unittest.TestCase):
    def test_split_visible_hidden(self):
        source = "# TEST\nassert type(q1) == int\n### BEGIN HIDDEN TESTS\nassert q1 == 42\n### END HIDDEN TESTS"
        vis, hid = split_test_content(source)
        self.assertEqual(vis, ["assert type(q1) == int"])
        self.assertEqual(hid, ["assert q1 == 42"])

    def test_visible_only(self):
        source = "assert x == 1\nassert y == 2"
        vis, hid = split_test_content(source)
        self.assertEqual(vis, ["assert x == 1", "assert y == 2"])
        self.assertEqual(hid, [])


class TestOtterDelimiters(unittest.TestCase):
    def test_identify_delimiter(self):
        self.assertEqual(identify_delimiter(make_raw("# BEGIN QUESTION\nname: q1")), "begin_question")
        self.assertEqual(identify_delimiter(make_raw("# END QUESTION")), "end_question")
        self.assertIsNone(identify_delimiter(make_code("# BEGIN QUESTION")))
        self.assertIsNone(identify_delimiter(make_markdown("text")))

    def test_is_otter_infrastructure(self):
        self.assertTrue(is_otter_infrastructure(make_raw("# ASSIGNMENT CONFIG\nname: hw1")))
        self.assertTrue(is_otter_infrastructure(make_raw("# BEGIN QUESTION\nname: q1")))
        self.assertFalse(is_otter_infrastructure(make_markdown("### Question 1")))

    def test_find_question_blocks(self):
        cells = [
            make_raw("# BEGIN QUESTION\nname: q1\npoints: 1"),
            make_code("q1 = 1 # SOLUTION"),
            make_raw("# END QUESTION"),
            make_markdown("between"),
            make_raw("# BEGIN QUESTION\nname: q2\npoints: 2"),
            make_code("q2 = 2 # SOLUTION"),
            make_raw("# END QUESTION"),
        ]
        blocks = find_question_blocks(cells)
        self.assertEqual(blocks, [(0, 2), (4, 6)])


if __name__ == "__main__":
    unittest.main()
