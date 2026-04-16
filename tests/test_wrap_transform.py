import unittest
import sys
import json
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "skills" / "refactoring-nbgrader-to-otter" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).parent))

from _lib import (
    get_source, identify_delimiter, find_question_blocks,
    is_solution_cell, is_test_cell, is_inside_question_block,
)
from fixtures import (
    make_notebook, make_markdown, make_code, make_raw,
    make_solution_cell, make_test_cell,
    simple_nbgrader_notebook, multi_solution_notebook,
    notebook_with_provided_computation, no_test_question_notebook,
    write_notebook, read_notebook,
)


def run_wrap_transform(nb):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.ipynb"
        write_notebook(nb, path)
        from wrap_transform import transform
        transform(str(path))
        return read_notebook(path)


class TestBasicTransform(unittest.TestCase):
    def test_simple_notebook_preserves_all_cells(self):
        original = simple_nbgrader_notebook()
        original_md_sources = [get_source(c) for c in original["cells"] if c["cell_type"] == "markdown"]
        result = run_wrap_transform(original)
        result_md_sources = [get_source(c) for c in result["cells"] if c["cell_type"] == "markdown"]
        self.assertEqual(original_md_sources, result_md_sources)

    def test_simple_notebook_has_question_blocks(self):
        result = run_wrap_transform(simple_nbgrader_notebook())
        blocks = find_question_blocks(result["cells"])
        self.assertEqual(len(blocks), 2)

    def test_solution_markers_added(self):
        result = run_wrap_transform(simple_nbgrader_notebook())
        solution_cells = [c for c in result["cells"] if c["cell_type"] == "code" and "# SOLUTION" in get_source(c)]
        self.assertGreaterEqual(len(solution_cells), 2)

    def test_test_cells_split(self):
        result = run_wrap_transform(simple_nbgrader_notebook())
        hidden_cells = [c for c in result["cells"] if c["cell_type"] == "code" and get_source(c).startswith("# HIDDEN")]
        self.assertGreaterEqual(len(hidden_cells), 1)

    def test_nbgrader_markers_stripped_from_solution(self):
        result = run_wrap_transform(simple_nbgrader_notebook())
        for c in result["cells"]:
            if c["cell_type"] == "code":
                src = get_source(c)
                self.assertNotIn("### BEGIN SOLUTION", src)
                self.assertNotIn("### END SOLUTION", src)


class TestMultiSolution(unittest.TestCase):
    def test_interleaved_markdown_preserved(self):
        result = run_wrap_transform(multi_solution_notebook())
        result_sources = [get_source(c) for c in result["cells"]]
        self.assertIn("Now compute the standard deviation.", result_sources)
        self.assertIn("First compute the mean.", result_sources)

    def test_both_solutions_inside_question_block(self):
        result = run_wrap_transform(multi_solution_notebook())
        blocks = find_question_blocks(result["cells"])
        self.assertEqual(len(blocks), 2)


class TestNoTestQuestion(unittest.TestCase):
    def test_no_tests_block(self):
        result = run_wrap_transform(no_test_question_notebook())
        cells = result["cells"]
        blocks = find_question_blocks(cells)
        self.assertEqual(len(blocks), 2)
        q1_begin, q1_end = blocks[0]
        q1_cells = cells[q1_begin:q1_end + 1]
        q1_sources = [get_source(c) for c in q1_cells]
        self.assertFalse(any("# BEGIN TESTS" in s for s in q1_sources))


class TestProvidedComputation(unittest.TestCase):
    def test_multiple_gap_cells_preserve_order(self):
        nb = make_notebook([
            make_markdown("# Assignment"),
            make_markdown("### Question 1: Compute"),
            make_solution_cell("### BEGIN SOLUTION ###\nmeans = [1, 2, 3]\n### END SOLUTION ###"),
            make_test_cell("assert len(means) == 3", points=1),
            make_code("cell_a = 1"),
            make_code("cell_b = 2"),
            make_markdown("### Question 2: Next"),
            make_solution_cell("### BEGIN SOLUTION ###\nq2 = 10\n### END SOLUTION ###"),
            make_test_cell("assert q2 == 10", points=1),
        ])
        result = run_wrap_transform(nb)
        cells = result["cells"]
        relocated = [(i, get_source(c)) for i, c in enumerate(cells)
                     if c["cell_type"] == "code" and get_source(c) in ("cell_a = 1", "cell_b = 2")]
        self.assertEqual(len(relocated), 2)
        self.assertLess(relocated[0][0], relocated[1][0], "cell_a should appear before cell_b")
        self.assertEqual(relocated[0][1], "cell_a = 1")
        self.assertEqual(relocated[1][1], "cell_b = 2")

    def test_code_cell_relocated_inside_question(self):
        result = run_wrap_transform(notebook_with_provided_computation())
        cells = result["cells"]
        for i, c in enumerate(cells):
            src = get_source(c)
            if "standardized" in src and c["cell_type"] == "code" and "# SOLUTION" not in src:
                self.assertTrue(is_inside_question_block(cells, i),
                    f"Provided computation cell at index {i} should be inside a question block")
                break


class TestIdempotence(unittest.TestCase):
    def test_double_run_identical(self):
        nb = simple_nbgrader_notebook()
        first = run_wrap_transform(nb)
        second = run_wrap_transform(first)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))


class TestQuestionConfig(unittest.TestCase):
    def test_begin_question_has_yaml(self):
        result = run_wrap_transform(simple_nbgrader_notebook())
        for c in result["cells"]:
            if identify_delimiter(c) == "begin_question":
                src = get_source(c)
                self.assertIn("name:", src)
                self.assertIn("points:", src)
                break

    def test_question_name_from_header(self):
        result = run_wrap_transform(simple_nbgrader_notebook())
        names = []
        for c in result["cells"]:
            if identify_delimiter(c) == "begin_question":
                for line in get_source(c).split("\n"):
                    if line.startswith("name:"):
                        names.append(line.split(":")[1].strip())
        self.assertIn("q1", names)
        self.assertIn("q2", names)


if __name__ == "__main__":
    unittest.main()
