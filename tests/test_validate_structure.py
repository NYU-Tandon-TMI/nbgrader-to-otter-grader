import unittest
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "skills" / "refactoring-nbgrader-to-otter" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).parent))

from fixtures import (
    make_notebook, make_markdown, make_code, make_raw,
    write_notebook,
)


class TestSkipCleanup(unittest.TestCase):
    def _make_nb_with_metadata(self):
        return make_notebook([
            make_raw("# ASSIGNMENT CONFIG\nname: test\nenvironment: environment.yml\nfiles:\n  - data.csv\ngenerate:\n  pdf: false"),
            make_raw("# BEGIN QUESTION\nname: q1\npoints: 1\nall_or_nothing: true"),
            make_raw("# BEGIN SOLUTION"),
            {
                "cell_type": "code", "execution_count": None,
                "metadata": {"nbgrader": {"solution": True}},
                "outputs": [], "source": "q1 = 1 # SOLUTION",
            },
            make_raw("# END SOLUTION"),
            make_raw("# BEGIN TESTS"),
            make_code("assert q1 == 1"),
            make_raw("# END TESTS"),
            make_raw("# END QUESTION"),
        ])

    def test_skip_cleanup_ignores_metadata(self):
        nb = self._make_nb_with_metadata()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.ipynb"
            write_notebook(nb, path)
            (Path(tmp) / "environment.yml").touch()
            (Path(tmp) / "data.csv").touch()
            from validate_structure import validate
            exit_code = validate(str(path), cwd=tmp, skip_cleanup=True)
            self.assertEqual(exit_code, 0)

    def test_full_validation_catches_metadata(self):
        nb = self._make_nb_with_metadata()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.ipynb"
            write_notebook(nb, path)
            (Path(tmp) / "environment.yml").touch()
            (Path(tmp) / "data.csv").touch()
            from validate_structure import validate
            exit_code = validate(str(path), cwd=tmp, skip_cleanup=False)
            self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
