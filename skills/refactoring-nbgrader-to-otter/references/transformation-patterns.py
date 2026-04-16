"""
Reusable code patterns for nbgrader to otter-grader transformations.

This file contains helper functions extracted from successful transformation scripts.
Use these patterns as reference when performing LLM-assisted transformations.

These are NOT meant to be imported - they are documentation/reference only.
Copy and adapt these patterns as needed for your transformation work.
"""

import json
import re


# ---------------------------------------------------------------------------
# Pattern 1: Finding Solution Cells (Skip Already-Transformed Blocks)
# ---------------------------------------------------------------------------

def find_solution_cells(cells, start_idx=0):
    """
    Find all untransformed solution cells (cells with nbgrader.solution=True)
    that are NOT already within a transformed question block.

    This is critical for incremental transformations - you don't want to
    re-transform cells that are already inside BEGIN QUESTION / END QUESTION blocks.

    Usage:
        cells = notebook['cells']
        untransformed = find_solution_cells(cells)
        if untransformed:
            next_solution_idx = untransformed[0]
    """
    solutions = []
    in_transformed_block = False

    for i in range(start_idx, len(cells)):
        cell = cells[i]
        source = cell['source'] if isinstance(cell['source'], str) else ''.join(cell['source'])

        # Check if we're entering or exiting a transformed block
        if cell['cell_type'] == 'raw':
            if source.strip().startswith('# BEGIN QUESTION'):
                in_transformed_block = True
            elif source.strip().startswith('# END QUESTION'):
                in_transformed_block = False

        # Only add solutions that are NOT in a transformed block
        if not in_transformed_block:
            nbg = cell.get('metadata', {}).get('nbgrader', {})
            if nbg.get('solution', False):
                solutions.append(i)

    return solutions


# ---------------------------------------------------------------------------
# Pattern 2: Locate Test Cell with Extended Search
# ---------------------------------------------------------------------------

def find_test_cell_for_solution(cells, solution_idx, max_distance=15):
    """
    Find the test cell that follows a solution cell.

    For multi-cell solutions, the test may be several cells away.
    We search up to max_distance cells ahead to handle this.

    Usage:
        test_idx = find_test_cell_for_solution(cells, solution_idx)
        if test_idx is None:
            print("ERROR: No test cell found")
    """
    # Look up to max_distance cells ahead
    for i in range(solution_idx + 1, min(solution_idx + max_distance, len(cells))):
        cell = cells[i]
        nbg = cell.get('metadata', {}).get('nbgrader', {})
        if nbg.get('grade', False):
            return i
    return None


# ---------------------------------------------------------------------------
# Pattern 3: Multi-Cell Solution Support
# ---------------------------------------------------------------------------

def find_all_solution_cells_for_question(cells, first_solution_idx, test_idx):
    """
    Find all solution cells between first solution and test cell.

    This handles questions where the solution is split across multiple cells
    (e.g., Q2.1, Q2.2 as separate code cells that are part of the same question).

    Usage:
        first_sol = find_solution_cells(cells)[0]
        test = find_test_cell_for_solution(cells, first_sol)
        all_solutions = find_all_solution_cells_for_question(cells, first_sol, test)
        # all_solutions is [first_sol, ...other solution indices]
    """
    solution_cells = [first_solution_idx]

    for i in range(first_solution_idx + 1, test_idx):
        cell = cells[i]
        nbg = cell.get('metadata', {}).get('nbgrader', {})
        if nbg.get('solution', False):
            solution_cells.append(i)

    return solution_cells


# ---------------------------------------------------------------------------
# Pattern 4: Extract Solution Code (Clean NBGrader Markers)
# ---------------------------------------------------------------------------

def extract_solution_code(source):
    """
    Extract actual solution from between nbgrader markers.

    Removes:
    - ### BEGIN SOLUTION ### / ### END SOLUTION ###
    - Placeholder assignments like "var = ..."
    - Bare ellipsis (...)

    Usage:
        cell_source = cells[solution_idx]['source']
        if isinstance(cell_source, list):
            cell_source = ''.join(cell_source)
        clean_solution = extract_solution_code(cell_source)
        # Now add # SOLUTION marker: f"{clean_solution} # SOLUTION"
    """
    # Try to find ### BEGIN SOLUTION ### ... ### END SOLUTION ###
    match = re.search(
        r'###?\s*BEGIN\s+SOLUTION\s*###?\s*\n(.+?)\n###?\s*END\s+SOLUTION\s*###?',
        source,
        re.DOTALL | re.IGNORECASE
    )

    if match:
        return match.group(1).strip()

    # Fallback: remove placeholder lines
    lines = []
    for line in source.split('\n'):
        stripped = line.strip()

        # Skip nbgrader markers
        if re.match(r'###?\s*BEGIN\s+SOLUTION', stripped, re.IGNORECASE):
            continue
        if re.match(r'###?\s*END\s+SOLUTION', stripped, re.IGNORECASE):
            continue

        # Skip placeholder assignments
        if re.match(r'^\w+\s*=\s*\.\.\.\s*$', stripped):
            continue

        # Skip bare ellipsis
        if stripped in ('...', '…'):
            continue

        lines.append(line)

    return '\n'.join(lines).strip()


# ---------------------------------------------------------------------------
# Pattern 5: Split Tests (Visible vs Hidden)
# ---------------------------------------------------------------------------

def split_tests(source):
    """
    Split test source into visible and hidden tests.

    Visible tests appear in student notebook.
    Hidden tests only appear in autograder.

    Returns: (visible_str, hidden_str)

    Usage:
        test_source = cells[test_idx]['source']
        if isinstance(test_source, list):
            test_source = ''.join(test_source)
        visible, hidden = split_tests(test_source)

        # Then create test cells:
        # - Code cell with visible tests
        # - Code cell with "# HIDDEN\n" + hidden tests
    """
    visible = []
    hidden = []
    in_hidden = False

    for line in source.split('\n'):
        stripped = line.strip()

        # Check for hidden test markers
        if stripped in ('### BEGIN HIDDEN TESTS ###', '# BEGIN HIDDEN TESTS'):
            in_hidden = True
            continue
        if stripped in ('### END HIDDEN TESTS ###', '# END HIDDEN TESTS'):
            in_hidden = False
            continue

        # Skip # TEST comments
        if re.match(r'^\s*#\s*TEST\s*$', stripped, re.IGNORECASE):
            continue

        # Skip blank lines
        if not stripped:
            continue

        # Append to appropriate list
        if in_hidden:
            hidden.append(line)
        else:
            visible.append(line)

    visible_str = '\n'.join(visible).strip() if visible else ''
    hidden_str = '\n'.join(hidden).strip() if hidden else ''

    return visible_str, hidden_str


# ---------------------------------------------------------------------------
# Pattern 6: Safe Cell Replacement (Reverse Deletion)
# ---------------------------------------------------------------------------

def apply_transformation(cells, new_cells, remove_indices, insert_at):
    """
    Safely replace cells by removing old ones and inserting new ones.

    CRITICAL: Remove cells in REVERSE order (highest index first) to avoid
    index shifting issues.

    Usage:
        # Build new_cells (list of cell dicts)
        # Identify remove_indices (list of cell indices to delete)
        # Choose insert_at (index where new cells should be inserted)

        apply_transformation(notebook['cells'], new_cells, remove_indices, insert_at)

        # Now notebook is modified in-place
    """
    # Remove old cells (in reverse order to maintain indices)
    for idx in sorted(remove_indices, reverse=True):
        del cells[idx]

    # Insert new cells at the specified position
    for i, new_cell in enumerate(new_cells):
        cells.insert(insert_at + i, new_cell)


# ---------------------------------------------------------------------------
# Pattern 7: Cell Constructors
# ---------------------------------------------------------------------------

def make_raw_cell(source):
    """Create a raw cell (for delimiters)."""
    return {
        "cell_type": "raw",
        "metadata": {},
        "source": source,
    }


def make_code_cell(source, outputs=None, metadata=None):
    """Create a code cell."""
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": metadata or {},
        "outputs": outputs or [],
        "source": source,
    }


# ---------------------------------------------------------------------------
# Pattern 8: Question Name Extraction
# ---------------------------------------------------------------------------

QUESTION_HEADER_RE = re.compile(r"###?\s*Question\s+(\d+)", re.IGNORECASE)


def extract_question_number(cells, before_index, lookback=15):
    """
    Extract question number from markdown cells before solution.

    Searches backwards up to lookback cells for a markdown cell containing
    "### Question N:" or "## Question N:".

    Usage:
        q_num = extract_question_number(cells, solution_idx)
        if q_num:
            question_name = f"q{q_num}"
    """
    for i in range(before_index - 1, max(0, before_index - lookback), -1):
        cell = cells[i]
        if cell.get("cell_type") != "markdown":
            continue

        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)

        m = QUESTION_HEADER_RE.search(source)
        if m:
            return int(m.group(1))

    return None


# ---------------------------------------------------------------------------
# Pattern 9: Non-Functional Cell Categorization
# ---------------------------------------------------------------------------

def categorize_cells_in_question(cells, solution_indices, test_idx):
    """
    Categorize cells between first solution and first test into sections:
    - before_first_solution: markdown/read-only code before any solution
    - solution_cells: the actual solution cells
    - between_solutions_and_tests: markdown/explanations between solution and tests

    This preserves the pedagogical structure while wrapping solutions/tests properly.

    Usage:
        first_sol = solution_indices[0]
        categories = categorize_cells_in_question(cells, solution_indices, test_idx)

        # Build transformed structure:
        # BEGIN QUESTION
        # ... categories['before_first_solution']
        # BEGIN SOLUTION
        # ... categories['solution_cells']
        # END SOLUTION
        # ... categories['between_solutions_and_tests']
        # BEGIN TESTS
        # ...
    """
    result = {
        'before_first_solution': [],
        'solution_cells': [],
        'between_solutions_and_tests': []
    }

    first_solution_idx = solution_indices[0]
    last_solution_idx = solution_indices[-1]

    current_section = 'before'

    for i in range(first_solution_idx, test_idx):
        cell = cells[i]
        nbg = cell.get('metadata', {}).get('nbgrader', {})

        if nbg.get('solution', False):
            current_section = 'solution'
            result['solution_cells'].append(cell)
        else:
            # Non-solution cell
            if current_section == 'before':
                result['before_first_solution'].append(cell)
            elif current_section == 'solution':
                # After first solution started
                result['between_solutions_and_tests'].append(cell)

    return result


# ---------------------------------------------------------------------------
# Example: Complete Question Transformation
# ---------------------------------------------------------------------------

def transform_question_example(cells, solution_idx):
    """
    Example of a complete question transformation using all the patterns above.

    This is a reference implementation showing how to combine the patterns.
    """
    # 1. Find test cell
    test_idx = find_test_cell_for_solution(cells, solution_idx)
    if test_idx is None:
        raise ValueError("No test cell found")

    # 2. Find all solution cells for this question
    solution_indices = find_all_solution_cells_for_question(cells, solution_idx, test_idx)

    # 3. Extract question name
    q_num = extract_question_number(cells, solution_idx)
    question_name = f"q{q_num}" if q_num else "q_unknown"

    # 4. Get points from test cell
    nbg = cells[test_idx].get('metadata', {}).get('nbgrader', {})
    points = nbg.get('points', 1)

    # 5. Categorize cells
    categories = categorize_cells_in_question(cells, solution_indices, test_idx)

    # 6. Extract and clean solution code
    cleaned_solutions = []
    for idx in solution_indices:
        source = cells[idx].get('source', '')
        if isinstance(source, list):
            source = ''.join(source)
        cleaned = extract_solution_code(source)
        # Add # SOLUTION marker
        cleaned_solutions.append(f"{cleaned} # SOLUTION")

    # 7. Split test content
    test_source = cells[test_idx].get('source', '')
    if isinstance(test_source, list):
        test_source = ''.join(test_source)
    visible_tests, hidden_tests = split_tests(test_source)

    # 8. Build new cells
    new_cells = []

    # BEGIN QUESTION
    new_cells.append(make_raw_cell(
        f"# BEGIN QUESTION\nname: {question_name}\npoints: {points}\nall_or_nothing: true"
    ))

    # Cells before solution
    new_cells.extend(categories['before_first_solution'])

    # BEGIN SOLUTION
    new_cells.append(make_raw_cell("# BEGIN SOLUTION"))

    # Solution cells
    for i, solution_code in enumerate(cleaned_solutions):
        # Preserve original outputs if available
        original_cell = cells[solution_indices[i]]
        new_cells.append(make_code_cell(
            solution_code,
            outputs=original_cell.get('outputs', []),
            metadata=original_cell.get('metadata', {})  # Preserve nbgrader metadata!
        ))

    # END SOLUTION
    new_cells.append(make_raw_cell("# END SOLUTION"))

    # Cells between solution and tests
    new_cells.extend(categories['between_solutions_and_tests'])

    # BEGIN TESTS
    new_cells.append(make_raw_cell("# BEGIN TESTS"))

    # Visible tests
    if visible_tests:
        new_cells.append(make_code_cell(visible_tests))

    # Hidden tests
    if hidden_tests:
        new_cells.append(make_code_cell(f"# HIDDEN\n{hidden_tests}"))

    # END TESTS
    new_cells.append(make_raw_cell("# END TESTS"))

    # END QUESTION
    new_cells.append(make_raw_cell("# END QUESTION"))

    # 9. Apply transformation
    remove_indices = solution_indices + [test_idx]
    apply_transformation(cells, new_cells, remove_indices, solution_idx)

    return {
        'question_name': question_name,
        'points': points,
        'cells_added': len(new_cells),
        'cells_removed': len(remove_indices)
    }


# ---------------------------------------------------------------------------
# Notes and Best Practices
# ---------------------------------------------------------------------------

"""
BEST PRACTICES:

1. **Always Preserve Metadata During Transformation**
   - Keep cell.metadata.nbgrader intact on solution cells
   - Only strip metadata in Step 8 (final cleanup)
   - This allows incremental transformation of multiple questions

2. **Handle Multi-Cell Solutions**
   - Don't assume one question = one solution cell
   - Search between first solution and test for additional solution cells
   - Wrap ALL solution cells in a single BEGIN SOLUTION / END SOLUTION pair

3. **Preserve Non-Functional Cells**
   - Keep markdown explanations in their original positions
   - Keep read-only code cells that provide context
   - Only remove/replace solution and test cells

4. **Use Reverse Deletion**
   - When removing multiple cells, always delete in reverse order
   - This prevents index shifting issues

5. **Clean Solution Code Properly**
   - Remove ### BEGIN SOLUTION ### / ### END SOLUTION ###
   - Remove placeholder assignments (var = ...)
   - Remove bare ellipsis (...)
   - Preserve actual solution logic and formatting

6. **Split Tests Carefully**
   - Visible tests go in student notebook
   - Hidden tests go in autograder only
   - Remove # TEST comments (they're just markers)

7. **Validate After Each Question**
   - Run validate_structure.py after transforming each question
   - Catch errors early before they cascade
   - Don't batch-transform without validation

8. **Progress Tracking**
   - Count remaining untransformed solutions
   - Print informative progress messages
   - Make it easy to resume if interrupted
"""
