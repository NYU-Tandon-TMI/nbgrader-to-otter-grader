import sys
import json
import copy
import difflib
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _lib import (
    read_notebook, write_notebook, get_source,
    find_question_blocks, identify_delimiter,
    is_otter_infrastructure,
)
from diff_notebooks import normalize, extract_nonfunctional_cells, extract_candidate_cells


def build_anchor_map(original_cells, converted_cells):
    orig_nf = extract_nonfunctional_cells(original_cells)
    conv_cands = extract_candidate_cells(converted_cells)
    norm_conv = [(idx, normalize(get_source(cell))) for idx, cell in conv_cands]
    conv_used = set()
    anchor = {}
    for orig_idx, orig_cell in orig_nf:
        orig_norm = normalize(get_source(orig_cell))
        matched = False
        for ci, (conv_idx, conv_norm) in enumerate(norm_conv):
            if ci in conv_used:
                continue
            if orig_norm == conv_norm:
                anchor[orig_idx] = conv_idx
                conv_used.add(ci)
                matched = True
                break
        if not matched and len(orig_norm) >= 20:
            best_ratio = 0
            best_ci = None
            for ci, (conv_idx, conv_norm) in enumerate(norm_conv):
                if ci in conv_used:
                    continue
                ratio = difflib.SequenceMatcher(None, orig_norm, conv_norm).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_ci = ci
            if best_ratio >= 0.85 and best_ci is not None:
                anchor[orig_idx] = norm_conv[best_ci][0]
                conv_used.add(best_ci)
    return anchor


def fix_dropped(original_cells, converted_cells, dropped_cells, anchor_map):
    sorted_drops = sorted(dropped_cells, key=lambda d: d["original_index"])
    fixed = 0
    for drop in sorted_drops:
        orig_idx = drop["original_index"]
        orig_cell = original_cells[orig_idx]

        best_anchor_conv_idx = 0
        for oi, ci in sorted(anchor_map.items()):
            if oi < orig_idx:
                best_anchor_conv_idx = max(best_anchor_conv_idx, ci + 1)

        if best_anchor_conv_idx == 0:
            insert_pos = 1 if converted_cells and is_otter_infrastructure(converted_cells[0]) else 0
        else:
            insert_pos = best_anchor_conv_idx

        insert_pos = min(insert_pos, len(converted_cells))

        clean_cell = copy.deepcopy(orig_cell)
        clean_cell.get("metadata", {}).pop("nbgrader", None)

        converted_cells.insert(insert_pos, clean_cell)

        for oi in list(anchor_map.keys()):
            if anchor_map[oi] >= insert_pos:
                anchor_map[oi] += 1
        anchor_map[orig_idx] = insert_pos
        fixed += 1

    return fixed


def fix_misplaced(converted_cells, misplaced_cells):
    sorted_misplaced = sorted(misplaced_cells, key=lambda m: m["converted_index"], reverse=True)
    fixed = 0
    for mis in sorted_misplaced:
        ci = mis["converted_index"]
        if ci >= len(converted_cells):
            continue

        cell = converted_cells.pop(ci)
        blocks = find_question_blocks(converted_cells)

        target_block = None
        for begin, end in blocks:
            if end < ci or (end == ci and begin < ci):
                target_block = (begin, end)

        if target_block is None and blocks:
            target_block = blocks[-1]

        if target_block is None:
            converted_cells.insert(ci, cell)
            continue

        begin, end = target_block
        insert_pos = end
        for k in range(begin, end + 1):
            d = identify_delimiter(converted_cells[k])
            if d == "begin_tests":
                insert_pos = k
                break
            elif d == "end_question":
                insert_pos = k
                break

        converted_cells.insert(insert_pos, cell)
        fixed += 1

    return fixed


def fix(original_path, converted_path, report_path):
    with open(report_path, "r") as f:
        report = json.load(f)

    orig_nb = read_notebook(original_path)
    conv_nb = read_notebook(converted_path)

    dropped_cells = report.get("dropped_cells", [])
    misplaced_cells = report.get("misplaced_cells", [])

    drops_fixed = 0
    misplaced_fixed = 0

    if dropped_cells:
        anchor_map = build_anchor_map(orig_nb["cells"], conv_nb["cells"])
        drops_fixed = fix_dropped(orig_nb["cells"], conv_nb["cells"], dropped_cells, anchor_map)

    if misplaced_cells:
        misplaced_fixed = fix_misplaced(conv_nb["cells"], misplaced_cells)

    write_notebook(conv_nb, converted_path)
    print(f"Fixed {drops_fixed} dropped cell(s), {misplaced_fixed} misplaced cell(s)", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Deterministic auto-fix for diff findings")
    parser.add_argument("original", help="Path to original nbgrader notebook")
    parser.add_argument("converted", help="Path to converted otter notebook")
    parser.add_argument("report", help="Path to diff report JSON")
    args = parser.parse_args()
    fix(args.original, args.converted, args.report)


if __name__ == "__main__":
    main()
