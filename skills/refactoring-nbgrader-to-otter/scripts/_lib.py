import json
import re


# ---------------------------------------------------------------------------
# Notebook I/O
# ---------------------------------------------------------------------------

def read_notebook(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_notebook(nb, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)


def get_source(cell):
    src = cell.get("source", [])
    return "".join(src) if isinstance(src, list) else (src or "")


# ---------------------------------------------------------------------------
# NBGrader metadata
# ---------------------------------------------------------------------------

def get_nbgrader_meta(cell):
    return cell.get("metadata", {}).get("nbgrader", {})


def is_solution_cell(cell):
    return bool(get_nbgrader_meta(cell).get("solution", False))


def is_test_cell(cell):
    return bool(get_nbgrader_meta(cell).get("grade", False))


def get_points(cell, default=0):
    meta = get_nbgrader_meta(cell)
    try:
        p = int(meta.get("points", default))
        return p if p >= 0 else default
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Question discovery
# ---------------------------------------------------------------------------

QUESTION_HEADER_RE = re.compile(r"#{1,6}\s*Question\s+(\d+)", re.IGNORECASE)


def find_question_header(cells, before_index):
    for i in range(before_index - 1, -1, -1):
        cell = cells[i]
        if cell.get("cell_type") != "markdown":
            continue
        src = get_source(cell)
        m = QUESTION_HEADER_RE.search(src)
        if m:
            return int(m.group(1)), i
    return None, None


def is_inside_question_block(cells, idx):
    for i in range(idx - 1, -1, -1):
        cell = cells[i]
        if cell.get("cell_type") == "raw":
            source = get_source(cell).strip()
            if source.startswith("# END QUESTION"):
                return False
            if source.startswith("# BEGIN QUESTION"):
                return True
    return False


# ---------------------------------------------------------------------------
# NBGrader marker stripping
# ---------------------------------------------------------------------------

NBGRADER_SOLUTION_MARKERS = [
    re.compile(r"^\s*###?\s*BEGIN\s+SOLUTION\s*#*\s*$", re.IGNORECASE),
    re.compile(r"^\s*###?\s*END\s+SOLUTION\s*#*\s*$", re.IGNORECASE),
]

PLACEHOLDER_RE = re.compile(r"^\s*\w[\w\s]*=\s*\.\.\.\s*$")
BARE_ELLIPSIS_RE = re.compile(r"^\s*(\.\.\.|…)\s*$")


def strip_solution_markers(source):
    lines = source.split("\n")
    cleaned = []
    for line in lines:
        if any(p.match(line) for p in NBGRADER_SOLUTION_MARKERS):
            continue
        if PLACEHOLDER_RE.match(line.strip()):
            continue
        if BARE_ELLIPSIS_RE.match(line.strip()):
            continue
        cleaned.append(line)
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    return "\n".join(cleaned)


# ---------------------------------------------------------------------------
# Test cell processing
# ---------------------------------------------------------------------------

HIDDEN_BEGIN_PATTERNS = [
    "### BEGIN HIDDEN TESTS", "###BEGIN HIDDEN TESTS",
    "# BEGIN HIDDEN TESTS", "#BEGIN HIDDEN TESTS",
]
HIDDEN_END_PATTERNS = [
    "### END HIDDEN TESTS", "###END HIDDEN TESTS",
    "# END HIDDEN TESTS", "#END HIDDEN TESTS",
]
TEST_COMMENT_RE = re.compile(r"^\s*#\s*TEST\s*$", re.IGNORECASE)


def split_test_content(source):
    lines = source.split("\n")
    visible, hidden = [], []
    in_hidden = False

    for line in lines:
        stripped = line.strip()
        if TEST_COMMENT_RE.match(stripped):
            continue
        if any(pat in stripped for pat in HIDDEN_BEGIN_PATTERNS):
            in_hidden = True
            continue
        if any(pat in stripped for pat in HIDDEN_END_PATTERNS):
            in_hidden = False
            continue
        if not stripped:
            continue
        (hidden if in_hidden else visible).append(line)

    return visible, hidden


# ---------------------------------------------------------------------------
# Cell constructors
# ---------------------------------------------------------------------------

def make_raw_cell(source):
    return {"cell_type": "raw", "metadata": {}, "source": source}


def make_code_cell(source, outputs=None, metadata=None):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": metadata or {},
        "outputs": outputs or [],
        "source": source,
    }


# ---------------------------------------------------------------------------
# Otter delimiter detection
# ---------------------------------------------------------------------------

OTTER_DELIMITERS = {
    "# BEGIN QUESTION": "begin_question",
    "# END QUESTION": "end_question",
    "# BEGIN SOLUTION": "begin_solution",
    "# END SOLUTION": "end_solution",
    "# BEGIN TESTS": "begin_tests",
    "# END TESTS": "end_tests",
}


def identify_delimiter(cell):
    if cell.get("cell_type") != "raw":
        return None
    src = get_source(cell).strip()
    first_line = src.split("\n")[0].strip() if src else ""
    for pattern, dtype in OTTER_DELIMITERS.items():
        if first_line == pattern or first_line.startswith(pattern + "\n"):
            return dtype
    return None


def is_otter_infrastructure(cell):
    src = get_source(cell).strip()
    if cell.get("cell_type") == "raw":
        if src.startswith("# ASSIGNMENT CONFIG"):
            return True
        if identify_delimiter(cell) is not None:
            return True
    if cell.get("cell_type") == "code":
        if "import otter" in src and "otter.Notebook" in src:
            return True
    return False


def find_question_blocks(cells):
    blocks = []
    i = 0
    while i < len(cells):
        d = identify_delimiter(cells[i])
        if d == "begin_question":
            begin = i
            j = i + 1
            while j < len(cells):
                if identify_delimiter(cells[j]) == "end_question":
                    blocks.append((begin, j))
                    break
                j += 1
            i = j + 1
        else:
            i += 1
    return blocks
