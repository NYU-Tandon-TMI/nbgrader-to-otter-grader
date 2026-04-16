import sys
import json
import re
import difflib
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _lib import (
    read_notebook, get_source, is_solution_cell, is_test_cell,
    is_otter_infrastructure, find_question_blocks, identify_delimiter,
    QUESTION_HEADER_RE,
)


def normalize(text):
    lines = text.strip().splitlines()
    normalized = []
    for line in lines:
        line = re.sub(r"\s+", " ", line.strip())
        line = re.sub(r"^#{1,6}\s*", "# ", line)
        normalized.append(line)
    return "\n".join(normalized)


def extract_nonfunctional_cells(cells):
    result = []
    for i, cell in enumerate(cells):
        if is_solution_cell(cell) or is_test_cell(cell):
            continue
        if is_otter_infrastructure(cell):
            continue
        result.append((i, cell))
    return result


def extract_candidate_cells(cells):
    result = []
    for i, cell in enumerate(cells):
        if is_otter_infrastructure(cell):
            continue
        result.append((i, cell))
    return result


def content_diff(original_path, converted_path):
    orig_nb = read_notebook(original_path)
    conv_nb = read_notebook(converted_path)

    orig_cells = extract_nonfunctional_cells(orig_nb["cells"])
    conv_cells = extract_candidate_cells(conv_nb["cells"])

    conv_used = set()
    dropped = []
    matched_count = 0

    norm_orig = [(idx, cell, normalize(get_source(cell))) for idx, cell in orig_cells]
    norm_conv = [(idx, cell, normalize(get_source(cell))) for idx, cell in conv_cells]

    for orig_idx, orig_cell, orig_norm in norm_orig:
        found = False
        for ci, (conv_idx, conv_cell, conv_norm) in enumerate(norm_conv):
            if ci in conv_used:
                continue
            if orig_norm == conv_norm:
                conv_used.add(ci)
                matched_count += 1
                found = True
                break

        if not found and len(orig_norm) >= 20:
            best_ratio = 0
            best_ci = None
            for ci, (conv_idx, conv_cell, conv_norm) in enumerate(norm_conv):
                if ci in conv_used:
                    continue
                ratio = difflib.SequenceMatcher(None, orig_norm, conv_norm).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_ci = ci
            if best_ratio >= 0.85 and best_ci is not None:
                conv_used.add(best_ci)
                matched_count += 1
                found = True

        if not found:
            preview = get_source(orig_cell)[:80].replace("\n", " ")
            dropped.append({
                "original_index": orig_idx,
                "cell_type": orig_cell.get("cell_type", "unknown"),
                "preview": preview,
                "context": f"Original cell index {orig_idx}",
                "severity": "error",
            })

    return dropped, matched_count, len(orig_cells)


def structural_gap_analysis(cells):
    misplaced = []
    blocks = find_question_blocks(cells)
    if not blocks:
        return misplaced

    first_question_start = blocks[0][0]

    for b in range(len(blocks) - 1):
        _, end_q = blocks[b]
        next_begin, _ = blocks[b + 1]
        for i in range(end_q + 1, next_begin):
            cell = cells[i]
            if cell.get("cell_type") == "code" and not is_test_cell(cell):
                preview = get_source(cell)[:80].replace("\n", " ")
                misplaced.append({
                    "converted_index": i,
                    "cell_type": "code",
                    "preview": preview,
                    "context": f"Between END QUESTION (cell {end_q}) and BEGIN QUESTION (cell {next_begin})",
                    "severity": "warning",
                })

    for i, cell in enumerate(cells):
        if cell.get("cell_type") != "markdown":
            continue
        src = get_source(cell)
        if QUESTION_HEADER_RE.search(src):
            inside = any(begin <= i <= end for begin, end in blocks)
            if not inside and i >= first_question_start:
                preview = src[:80].replace("\n", " ")
                misplaced.append({
                    "converted_index": i,
                    "cell_type": "markdown",
                    "preview": preview,
                    "context": "Question header outside question block",
                    "severity": "warning",
                })

    return misplaced


def diff(original_path, converted_path):
    dropped, matched, total = content_diff(original_path, converted_path)
    conv_nb = read_notebook(converted_path)
    misplaced = structural_gap_analysis(conv_nb["cells"])
    status = "pass" if not dropped and not misplaced else "fail"
    return {
        "status": status,
        "dropped_cells": dropped,
        "misplaced_cells": misplaced,
        "summary": {
            "total_original_nonfunctional": total,
            "matched": matched,
            "dropped": len(dropped),
            "misplaced": len(misplaced),
        },
    }


def diff_converted_only(converted_path):
    conv_nb = read_notebook(converted_path)
    misplaced = structural_gap_analysis(conv_nb["cells"])
    status = "pass" if not misplaced else "fail"
    return {
        "status": status,
        "dropped_cells": [],
        "misplaced_cells": misplaced,
        "summary": {
            "total_original_nonfunctional": 0,
            "matched": 0,
            "dropped": 0,
            "misplaced": len(misplaced),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Content diff evaluator for notebook conversion")
    parser.add_argument("original", nargs="?", help="Path to original nbgrader notebook")
    parser.add_argument("converted", help="Path to converted otter notebook")
    parser.add_argument("--converted-only", action="store_true", help="Structural analysis only")
    args = parser.parse_args()

    if args.converted_only:
        result = diff_converted_only(args.converted)
    else:
        if not args.original:
            parser.error("original notebook path required (or use --converted-only)")
        result = diff(args.original, args.converted)

    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
