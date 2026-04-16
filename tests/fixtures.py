import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "skills" / "refactoring-nbgrader-to-otter" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def make_notebook(cells):
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "cells": cells,
    }


def make_markdown(source):
    return {"cell_type": "markdown", "metadata": {}, "source": source}


def make_code(source, outputs=None, metadata=None):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": metadata or {},
        "outputs": outputs or [],
        "source": source,
    }


def make_raw(source):
    return {"cell_type": "raw", "metadata": {}, "source": source}


def make_solution_cell(source, outputs=None):
    return make_code(source, outputs=outputs, metadata={"nbgrader": {"solution": True, "grade": False}})


def make_test_cell(source, points=1):
    return make_code(source, metadata={"nbgrader": {"grade": True, "solution": False, "points": points}})


def make_grade_only_cell(source, points=1):
    return make_code(source, metadata={"nbgrader": {"grade": True, "solution": False, "points": points}})


def write_notebook(nb, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)


def read_notebook(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def simple_nbgrader_notebook():
    return make_notebook([
        make_markdown("# Homework 1"),
        make_markdown("### Question 1: Basic"),
        make_solution_cell("### BEGIN SOLUTION ###\nq1 = 42\n### END SOLUTION ###"),
        make_test_cell("# TEST\nassert type(q1) == int\n### BEGIN HIDDEN TESTS\nassert q1 == 42\n### END HIDDEN TESTS"),
        make_markdown("### Question 2: Multi-line"),
        make_markdown("Compute the area of a circle with radius 3."),
        make_solution_cell("### BEGIN SOLUTION ###\nimport math\narea = math.pi * 3 ** 2\n### END SOLUTION ###"),
        make_test_cell("assert isinstance(area, float)", points=2),
        make_test_cell("# TEST\n### BEGIN HIDDEN TESTS\nassert abs(area - 28.274) < 0.01\n### END HIDDEN TESTS", points=1),
        make_markdown("## End of homework"),
    ])


def multi_solution_notebook():
    return make_notebook([
        make_markdown("# Project"),
        make_markdown("### Question 1: Two-part"),
        make_markdown("First compute the mean."),
        make_solution_cell("### BEGIN SOLUTION ###\nmean_val = 5.0\n### END SOLUTION ###"),
        make_markdown("Now compute the standard deviation."),
        make_solution_cell("### BEGIN SOLUTION ###\nstd_val = 1.0\n### END SOLUTION ###"),
        make_test_cell("assert isinstance(mean_val, float)\nassert isinstance(std_val, float)", points=2),
        make_markdown("### Question 2: Simple"),
        make_solution_cell("q2 = ...\n### BEGIN SOLUTION ###\nq2 = True\n### END SOLUTION ###"),
        make_test_cell("assert q2 is True", points=1),
    ])


def notebook_with_provided_computation():
    return make_notebook([
        make_markdown("# Assignment"),
        make_markdown("### Question 1: Compute"),
        make_solution_cell("### BEGIN SOLUTION ###\nmeans = [1, 2, 3]\n### END SOLUTION ###"),
        make_test_cell("assert len(means) == 3", points=1),
        make_code("standardized = [x / max(means) for x in means]"),
        make_test_cell("assert len(standardized) == 3", points=1),
        make_markdown("### Question 2: Next"),
        make_solution_cell("### BEGIN SOLUTION ###\nq2 = 10\n### END SOLUTION ###"),
        make_test_cell("assert q2 == 10", points=1),
    ])


def no_test_question_notebook():
    return make_notebook([
        make_markdown("# Lab"),
        make_markdown("### Question 1: Explore"),
        make_solution_cell("### BEGIN SOLUTION ###\nexplore = 'done'\n### END SOLUTION ###"),
        make_markdown("### Question 2: Graded"),
        make_solution_cell("### BEGIN SOLUTION ###\nq2 = 5\n### END SOLUTION ###"),
        make_test_cell("assert q2 == 5", points=1),
    ])
