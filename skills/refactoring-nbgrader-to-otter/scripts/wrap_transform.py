import sys
import re
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _lib import (
    read_notebook, write_notebook, get_source,
    is_solution_cell, is_test_cell, get_points,
    find_question_header, is_inside_question_block,
    strip_solution_markers, split_test_content,
    make_raw_cell, make_code_cell, identify_delimiter,
    find_question_blocks, QUESTION_HEADER_RE,
)


def map_question_groups(cells):
    groups = []
    visited_solutions = set()
    i = 0
    while i < len(cells):
        cell = cells[i]
        if is_solution_cell(cell) and i not in visited_solutions and not is_inside_question_block(cells, i):
            solution_indices = [i]
            visited_solutions.add(i)
            j = i + 1
            while j < len(cells):
                if is_solution_cell(cells[j]):
                    solution_indices.append(j)
                    visited_solutions.add(j)
                    j += 1
                elif is_test_cell(cells[j]):
                    break
                else:
                    if cells[j].get("cell_type") == "markdown" and QUESTION_HEADER_RE.search(get_source(cells[j])):
                        break
                    k = j + 1
                    while k < len(cells) and not is_solution_cell(cells[k]) and not is_test_cell(cells[k]):
                        k += 1
                    if k < len(cells) and is_solution_cell(cells[k]):
                        has_new_question = False
                        for mid in range(j, k):
                            if cells[mid].get("cell_type") == "markdown" and QUESTION_HEADER_RE.search(get_source(cells[mid])):
                                has_new_question = True
                                break
                        if has_new_question:
                            break
                        j += 1
                    else:
                        break
            test_indices = []
            t = j
            while t < len(cells) and not is_solution_cell(cells[t]):
                if is_test_cell(cells[t]):
                    test_indices.append(t)
                t += 1
            q_num, header_idx = find_question_header(cells, solution_indices[0])
            if q_num is not None:
                q_name = f"q{q_num}"
            else:
                src = get_source(cells[solution_indices[0]])
                var_match = re.match(r"^(\w+)\s*=", strip_solution_markers(src))
                if var_match:
                    vm = re.match(r"^q(\d+)", var_match.group(1))
                    q_name = f"q{vm.group(1)}" if vm else var_match.group(1)
                else:
                    q_name = f"q{len(groups) + 1}"
            total_points = sum(get_points(cells[ti]) for ti in test_indices)
            groups.append({
                "name": q_name,
                "header_idx": header_idx,
                "solution_indices": solution_indices,
                "test_indices": test_indices,
                "points": total_points,
                "first_idx": header_idx if header_idx is not None else solution_indices[0],
                "last_idx": test_indices[-1] if test_indices else solution_indices[-1],
            })
            i = (test_indices[-1] if test_indices else solution_indices[-1]) + 1
        else:
            i += 1
    return groups


def transform_solution_content(source):
    cleaned = strip_solution_markers(source)
    if not cleaned:
        return "... # SOLUTION"
    lines = cleaned.split("\n")
    non_empty = [l for l in lines if l.strip()]
    if len(non_empty) == 1:
        return f"{non_empty[0]} # SOLUTION"
    else:
        return f"# SOLUTION\n{cleaned}"


def wrap_questions(cells, groups):
    offset = 0
    for group in groups:
        first = group["first_idx"] + offset
        sol_indices = [s + offset for s in group["solution_indices"]]
        test_indices = [t + offset for t in group["test_indices"]]
        last = group["last_idx"] + offset

        bq_cell = make_raw_cell(
            f"# BEGIN QUESTION\nname: {group['name']}\npoints: {group['points']}\nall_or_nothing: true"
        )
        cells.insert(first, bq_cell)
        offset += 1
        sol_indices = [s + 1 for s in sol_indices]
        test_indices = [t + 1 for t in test_indices]
        last += 1

        bs_pos = sol_indices[0]
        cells.insert(bs_pos, make_raw_cell("# BEGIN SOLUTION"))
        offset += 1
        sol_indices = [s + (1 if s >= bs_pos else 0) for s in sol_indices]
        test_indices = [t + 1 for t in test_indices]
        last += 1

        for si in sol_indices:
            cell = cells[si]
            cell["source"] = transform_solution_content(get_source(cell))

        es_pos = sol_indices[-1] + 1
        cells.insert(es_pos, make_raw_cell("# END SOLUTION"))
        offset += 1
        test_indices = [t + (1 if t >= es_pos else 0) for t in test_indices]
        last += 1

        if test_indices:
            all_visible, all_hidden = [], []
            for ti in test_indices:
                vis, hid = split_test_content(get_source(cells[ti]))
                all_visible.extend(vis)
                all_hidden.extend(hid)

            bt_pos = test_indices[0]
            cells.insert(bt_pos, make_raw_cell("# BEGIN TESTS"))
            offset += 1
            test_indices = [t + 1 for t in test_indices]
            last += 1

            for ti in sorted(test_indices, reverse=True):
                del cells[ti]
                offset -= 1
                last -= 1

            insert_pos = bt_pos + 1
            new_test_cells = []
            if all_visible:
                new_test_cells.append(make_code_cell("\n".join(all_visible)))
            if all_hidden:
                new_test_cells.append(make_code_cell("# HIDDEN\n" + "\n".join(all_hidden)))
            for j, tc in enumerate(new_test_cells):
                cells.insert(insert_pos + j, tc)
                offset += 1
                last += 1

            et_pos = insert_pos + len(new_test_cells)
            cells.insert(et_pos, make_raw_cell("# END TESTS"))
            offset += 1
            last += 1

        eq_pos = last + 1
        cells.insert(eq_pos, make_raw_cell("# END QUESTION"))
        offset += 1


def relocate_between_question_code_cells(cells):
    moved = True
    while moved:
        moved = False
        blocks = find_question_blocks(cells)
        if len(blocks) < 2:
            break
        for b in range(len(blocks) - 1):
            _, end_q = blocks[b]
            next_begin, _ = blocks[b + 1]

            gap_indices = [
                i for i in range(end_q + 1, next_begin)
                if cells[i].get("cell_type") == "code"
                and not is_test_cell(cells[i])
                and not is_solution_cell(cells[i])
            ]
            if not gap_indices:
                continue

            end_sol = None
            begin_tests = None
            end_question = end_q
            for k in range(blocks[b][0], end_q + 1):
                d = identify_delimiter(cells[k])
                if d == "end_solution":
                    end_sol = k
                elif d == "begin_tests":
                    begin_tests = k
                elif d == "end_question":
                    end_question = k

            if begin_tests is not None:
                insert_at = begin_tests
            elif end_sol is not None:
                insert_at = end_sol + 1
            else:
                insert_at = end_question

            to_insert = [cells[i] for i in gap_indices]
            for i in reversed(gap_indices):
                cells.pop(i)
            for j, cell in enumerate(to_insert):
                cells.insert(insert_at + j, cell)

            moved = True
            break


def transform(notebook_path):
    nb = read_notebook(notebook_path)
    cells = nb["cells"]
    groups = map_question_groups(cells)
    if not groups:
        print("No untransformed questions found.", file=sys.stderr)
        return
    print(f"Found {len(groups)} question(s) to transform", file=sys.stderr)
    wrap_questions(cells, groups)
    relocate_between_question_code_cells(cells)
    write_notebook(nb, notebook_path)
    for g in groups:
        tests_str = f", {len(g['test_indices'])} tests" if g["test_indices"] else ", no tests"
        print(f"  {g['name']}: {len(g['solution_indices'])} solution(s){tests_str}, {g['points']} pts", file=sys.stderr)
    print(f"Transform complete. {len(groups)} question(s) wrapped.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Lossless wrap-in-place transform for nbgrader notebooks")
    parser.add_argument("notebook", help="Path to the notebook")
    args = parser.parse_args()
    transform(args.notebook)


if __name__ == "__main__":
    main()
