#!/usr/bin/env python3
"""
verify_no_extras.py

Ensure that a set of split Python files contains **no new executable
symbols** compared with the original monolithic `behaviours.py`.

Usage:
    python verify_no_extras.py /path/to/original/behaviours.py /path/to/new_dir
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Iterable, Set


def collect_module_symbols(tree: ast.AST, module_name: str = "") -> Set[str]:
    """
    Return a set of canonical symbol names defined at module scope.

    We collect:
      • function defs     →  foo
      • class defs        →  Bar
          – and their methods as  Bar.method
      • assignments       →  CONST_X  (lhs identifiers only)
    """
    symbols: Set[str] = set()

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef):  # module-level
            symbols.add(node.name)
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef):
            symbols.add(node.name)
            # gather method names
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.add(f"{node.name}.{item.name}")
            self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbols.add(target.id)
            # no need to traverse deeper (values don’t matter)

    Visitor().visit(tree)
    return symbols


def load_symbols_from_file(path: Path) -> Set[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return collect_module_symbols(tree, path.stem)


def symbols_from_dir(directory: Path) -> Set[str]:
    return {
        sym for file in directory.rglob("*.py") for sym in load_symbols_from_file(file)
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check that splitting a behaviour file introduced no new code."
    )
    parser.add_argument("original", type=Path, help="Original behaviours.py")
    parser.add_argument(
        "new_path",
        type=Path,
        help="Directory containing the split *.py files (or a single file).",
    )
    args = parser.parse_args()

    if not args.original.exists():
        sys.exit(f"Original file not found: {args.original}")
    if not args.new_path.exists():
        sys.exit(f"Path not found: {args.new_path}")

    original_syms = load_symbols_from_file(args.original)
    new_syms = (
        symbols_from_dir(args.new_path)
        if args.new_path.is_dir()
        else load_symbols_from_file(args.new_path)
    )

    extras = sorted(new_syms - original_syms)

    if extras:
        print("❌  NEW SYMBOLS INTRODUCED!\n")
        for sym in extras:
            print("   +", sym)
        print(f"\nTotal extras: {len(extras)}")
        sys.exit(1)
    else:
        print("✅  OK – no new code detected.")
        sys.exit(0)


if __name__ == "__main__":
    main()
