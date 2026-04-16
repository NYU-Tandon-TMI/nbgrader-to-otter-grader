import unittest
import sys
import json
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "skills" / "refactoring-nbgrader-to-otter" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).parent))

from _lib import get_source, find_question_blocks, is_inside_question_block
from fixtures import (
    make_notebook, make_markdown, make_code, make_raw,
    write_notebook, read_notebook,
)


def run_fix(original_nb, converted_nb, report):
    with tempfile.TemporaryDirectory() as tmp:
        orig_path = Path(tmp) / "original.ipynb"
        conv_path = Path(tmp) / "converted.ipynb"
        report_path = Path(tmp) / "report.json"
        write_notebook(original_nb, orig_path)
        write_notebook(converted_nb, conv_path)
        with open(report_path, "w") as f:
            json.dump(report, f)
        from fix_cells import fix
        fix(str(orig_path), str(conv_path), str(report_path))
        return read_notebook(conv_path)


class TestDroppedCellFix(unittest.TestCase):
    def test_reinsert_dropped_cell(self):
        original = make_notebook([
            make_markdown("# Title"),
            make_markdown("### Instruction A"),
            make_markdown("### Instruction B"),
            make_markdown("### Instruction C"),
        ])
        converted = make_notebook([
            make_markdown("# Title"),
            make_markdown("### Instruction C"),
        ])
        report = {
            "dropped_cells": [
                {"original_index": 1, "cell_type": "markdown", "preview": "### Instruction A", "context": "", "severity": "error"},
                {"original_index": 2, "cell_type": "markdown", "preview": "### Instruction B", "context": "", "severity": "error"},
            ],
            "misplaced_cells": [],
        }
        result = run_fix(original, converted, report)
        sources = [get_source(c) for c in result["cells"]]
        self.assertIn("### Instruction A", sources)
        self.assertIn("### Instruction B", sources)
        self.assertEqual(sources.index("### Instruction A"), 1)
        self.assertEqual(sources.index("### Instruction B"), 2)


class TestDroppedCellMetadata(unittest.TestCase):
    def test_reinserted_cell_strips_nbgrader_metadata(self):
        original = make_notebook([
            make_markdown("# Title"),
            {
                "cell_type": "markdown",
                "metadata": {"nbgrader": {"solution": False}, "custom_key": "preserved"},
                "source": "### Important instruction",
            },
        ])
        converted = make_notebook([make_markdown("# Title")])
        report = {
            "dropped_cells": [
                {"original_index": 1, "cell_type": "markdown", "preview": "### Important instruction", "context": "", "severity": "error"},
            ],
            "misplaced_cells": [],
        }
        result = run_fix(original, converted, report)
        reinserted = next(c for c in result["cells"] if get_source(c) == "### Important instruction")
        self.assertNotIn("nbgrader", reinserted.get("metadata", {}))
        self.assertEqual(reinserted.get("metadata", {}).get("custom_key"), "preserved")


class TestMisplacedCellFix(unittest.TestCase):
    def test_move_inside_question_block(self):
        converted = make_notebook([
            make_raw("# BEGIN QUESTION\nname: q1\npoints: 1"),
            make_raw("# BEGIN SOLUTION"),
            make_code("q1 = 1 # SOLUTION"),
            make_raw("# END SOLUTION"),
            make_raw("# BEGIN TESTS"),
            make_code("assert q1 == 1"),
            make_raw("# END TESTS"),
            make_raw("# END QUESTION"),
            make_code("orphan = True"),
            make_raw("# BEGIN QUESTION\nname: q2\npoints: 1"),
            make_raw("# BEGIN SOLUTION"),
            make_code("q2 = 2 # SOLUTION"),
            make_raw("# END SOLUTION"),
            make_raw("# END QUESTION"),
        ])
        report = {
            "dropped_cells": [],
            "misplaced_cells": [
                {"converted_index": 8, "cell_type": "code", "preview": "orphan = True", "context": "Between q1 and q2", "severity": "warning"},
            ],
        }
        result = run_fix(make_notebook([]), converted, report)
        cells = result["cells"]
        for i, c in enumerate(cells):
            if get_source(c) == "orphan = True":
                self.assertTrue(is_inside_question_block(cells, i), f"Cell at {i} should be inside question block")
                break

    def test_move_before_end_question_when_no_tests(self):
        converted = make_notebook([
            make_raw("# BEGIN QUESTION\nname: q1\npoints: 0"),
            make_raw("# BEGIN SOLUTION"),
            make_code("q1 = 1 # SOLUTION"),
            make_raw("# END SOLUTION"),
            make_raw("# END QUESTION"),
            make_code("orphan = True"),
            make_raw("# BEGIN QUESTION\nname: q2\npoints: 1"),
            make_raw("# BEGIN SOLUTION"),
            make_code("q2 = 2 # SOLUTION"),
            make_raw("# END SOLUTION"),
            make_raw("# END QUESTION"),
        ])
        report = {
            "dropped_cells": [],
            "misplaced_cells": [
                {"converted_index": 5, "cell_type": "code", "preview": "orphan = True", "context": "Between q1 and q2", "severity": "warning"},
            ],
        }
        result = run_fix(make_notebook([]), converted, report)
        cells = result["cells"]
        for i, c in enumerate(cells):
            if get_source(c) == "orphan = True":
                self.assertTrue(is_inside_question_block(cells, i))
                break


if __name__ == "__main__":
    unittest.main()
