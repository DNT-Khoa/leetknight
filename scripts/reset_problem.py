#!/usr/bin/env python3
"""
Reset <slug>/Solution.java to the original starter code from .leetio.json.

Silent — no confirmation. The caller (the VS Code extension) is responsible
for prompting the user when the reset was manually triggered from the editor
toolbar; the panel-click and random-pick flows deliberately skip that prompt.

Usage:
  ./reset_problem.py <problem-slug>
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description="Reset Solution.java to its starter code.")
    ap.add_argument("problem", help="LeetCode problem slug (the folder name)")
    args = ap.parse_args()

    workspace = os.getcwd()
    problem_dir = os.path.join(workspace, args.problem)
    meta_path = os.path.join(problem_dir, ".leetio.json")
    solution_path = os.path.join(problem_dir, "Solution.java")

    if not os.path.isfile(meta_path):
        print(f"[error] missing {meta_path}. Re-scaffold with 'leet.io: New Problem'.", file=sys.stderr)
        return 1

    with open(meta_path) as fh:
        meta = json.load(fh)

    initial_code = meta.get("initialCode") or ""
    if not initial_code:
        print(f"[error] no initialCode in {meta_path}.", file=sys.stderr)
        return 1

    with open(solution_path, "w") as fh:
        fh.write(initial_code)
        if not initial_code.endswith("\n"):
            fh.write("\n")

    print(f"Reset: {solution_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
