import unittest
import sys
import json
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "skills" / "refactoring-nbgrader-to-otter" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).parent))

from _lib import get_source, find_question_blocks
from fixtures import (
    simple_nbgrader_notebook, multi_solution_notebook,
    notebook_with_provided_computation, no_test_question_notebook,
    write_notebook, read_notebook,
)
from wrap_transform import transform
from diff_notebooks import diff
from fix_cells import fix as fix_cells_fn
from validate_structure import validate


def run_full_pipeline(nb, max_iterations=3):
    with tempfile.TemporaryDirectory() as tmp:
        orig_path = Path(tmp) / "original.ipynb"
        work_path = Path(tmp) / "notebook.ipynb"
        write_notebook(nb, orig_path)
        write_notebook(nb, work_path)

        raw_config = (
            "# ASSIGNMENT CONFIG\nname: test\nenvironment: environment.yml\n"
            "files:\n  - data.csv\ngenerate:\n  pdf: false"
        )
        work_nb = read_notebook(work_path)
        work_nb["cells"].insert(0, {"cell_type": "raw", "metadata": {}, "source": raw_config})
        write_notebook(work_nb, work_path)
        (Path(tmp) / "environment.yml").touch()
        (Path(tmp) / "data.csv").touch()

        transform(str(work_path))

        prev_findings = float("inf")
        diff_result = None
        for iteration in range(max_iterations):
            val_exit = validate(str(work_path), cwd=tmp, skip_cleanup=True)
            diff_result = diff(str(orig_path), str(work_path))
            findings = diff_result["summary"]["dropped"] + diff_result["summary"]["misplaced"]

            if val_exit == 0 and diff_result["status"] == "pass":
                return {"status": "pass", "iterations": iteration + 1, "diff": diff_result}

            if findings >= prev_findings:
                return {"status": "not_converging", "iterations": iteration + 1, "diff": diff_result}

            if diff_result["status"] == "fail":
                report_path = Path(tmp) / "report.json"
                with open(report_path, "w") as f:
                    json.dump(diff_result, f)
                fix_cells_fn(str(orig_path), str(work_path), str(report_path))

            prev_findings = findings

        return {"status": "max_iterations", "iterations": max_iterations, "diff": diff_result}


class TestFullPipeline(unittest.TestCase):
    def test_simple_notebook(self):
        result = run_full_pipeline(simple_nbgrader_notebook())
        self.assertEqual(result["status"], "pass")
        self.assertLessEqual(result["iterations"], 2)

    def test_multi_solution_notebook(self):
        result = run_full_pipeline(multi_solution_notebook())
        self.assertEqual(result["status"], "pass")

    def test_notebook_with_computation(self):
        result = run_full_pipeline(notebook_with_provided_computation())
        self.assertEqual(result["status"], "pass")

    def test_no_test_question(self):
        result = run_full_pipeline(no_test_question_notebook())
        self.assertEqual(result["status"], "pass")

    def test_zero_drops_on_all_fixtures(self):
        fixtures = [
            simple_nbgrader_notebook(),
            multi_solution_notebook(),
            notebook_with_provided_computation(),
            no_test_question_notebook(),
        ]
        for i, nb in enumerate(fixtures):
            result = run_full_pipeline(nb)
            self.assertEqual(
                result["diff"]["summary"]["dropped"], 0,
                f"Fixture {i} has dropped cells: {result['diff']['dropped_cells']}"
            )


if __name__ == "__main__":
    unittest.main()
