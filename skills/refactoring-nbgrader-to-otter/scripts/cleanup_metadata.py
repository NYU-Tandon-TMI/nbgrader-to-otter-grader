#!/usr/bin/env python3
"""
Strip nbgrader metadata from transformed instructor notebook.
This is Step 8 (FINAL STEP) of the refactoring workflow.

Usage: python3 cleanup_metadata.py <notebook.ipynb>
"""

import json
import sys
import re


def cleanup_metadata(notebook_path):
    """Remove nbgrader metadata and orphaned markers."""
    with open(notebook_path, 'r', encoding='utf-8') as f:
        nb = json.load(f)

    cells_cleaned = 0
    markers_removed = 0

    # 1. Remove nbgrader metadata
    for cell in nb['cells']:
        if 'nbgrader' in cell.get('metadata', {}):
            del cell['metadata']['nbgrader']
            cells_cleaned += 1

    # 2. Remove orphaned nbgrader markers
    for cell in nb['cells']:
        source = cell.get('source', '')
        if isinstance(source, list):
            source = ''.join(source)

        original = source

        # Remove nbgrader markers
        source = re.sub(r'###\s*BEGIN\s+SOLUTION\s*###\s*\n?', '', source)
        source = re.sub(r'###\s*END\s+SOLUTION\s*###\s*\n?', '', source)
        source = re.sub(r'###\s*BEGIN\s+HIDDEN\s+TESTS\s*###\s*\n?', '', source)
        source = re.sub(r'###\s*END\s+HIDDEN\s+TESTS\s*###\s*\n?', '', source)
        source = re.sub(r'#\s*TEST\s*\n?', '', source)

        # Remove placeholder lines (e.g., "var = ...")
        lines = source.split('\n')
        cleaned_lines = []
        for line in lines:
            # Skip lines that are just variable assignment to ellipsis
            if not re.match(r'^\s*\w+\s*=\s*\.\.\.\s*$', line):
                cleaned_lines.append(line)
        source = '\n'.join(cleaned_lines)

        if source != original:
            cell['source'] = source
            markers_removed += 1

    # Write back
    with open(notebook_path, 'w', encoding='utf-8') as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)

    print(f"✓ Cleaned {cells_cleaned} cells (removed nbgrader metadata)")
    print(f"✓ Cleaned {markers_removed} cells (removed orphaned markers)")

    if cells_cleaned == 0 and markers_removed == 0:
        print("  (No metadata or markers found - notebook may already be clean)")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python3 cleanup_metadata.py <notebook.ipynb>", file=sys.stderr)
        print("\nThis is Step 8 (FINAL STEP) of the nbgrader-to-otter refactoring workflow.", file=sys.stderr)
        print("Only run this AFTER all questions have been transformed.", file=sys.stderr)
        sys.exit(1)

    cleanup_metadata(sys.argv[1])
