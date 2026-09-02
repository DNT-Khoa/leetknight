#!/usr/bin/env python3
"""
Scaffold canary for LeetKnight.

Runs scripts/new.py against a known-stable LeetCode problem (two-sum) and
verifies the produced files are non-empty and well-formed. If the scaffold
regressed (LeetCode's GraphQL schema changed, codeSnippets missing, etc.),
CI will fail.

Run locally:
    python3 tests/canary.py

Run from the project root.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

TARGET_URL = "https://leetcode.com/problems/two-sum/"
EXPECTED_SLUG = "two-sum"
REQUIRED_META_KEYS = ("questionId", "exampleTestcases", "initialCode", "url")

MAX_ATTEMPTS = 3
RETRY_SLEEP_SECONDS = 10


def run_canary(workspace: str) -> list[str]:
    """Returns list of failure messages (empty list = pass)."""
    last_stderr = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result = subprocess.run(
            ["./new.py", TARGET_URL],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            break
        last_stderr = result.stderr.strip() or result.stdout.strip()
        print(
            f"  attempt {attempt}/{MAX_ATTEMPTS} failed (rc={result.returncode}): "
            f"{last_stderr.splitlines()[-1] if last_stderr else '<no output>'}",
            flush=True,
        )
        if attempt < MAX_ATTEMPTS:
            # Clean the partially-written folder so the next attempt starts fresh.
            slug_dir = os.path.join(workspace, EXPECTED_SLUG)
            if os.path.isdir(slug_dir):
                shutil.rmtree(slug_dir, ignore_errors=True)
            time.sleep(RETRY_SLEEP_SECONDS)
    else:
        return [
            f"new.py exited non-zero after {MAX_ATTEMPTS} attempts. "
            f"Last error: {last_stderr or '<empty>'}"
        ]

    problem_dir = os.path.join(workspace, EXPECTED_SLUG)
    failures: list[str] = []

    if not os.path.isdir(problem_dir):
        return [f"no `{EXPECTED_SLUG}/` directory created"]

    for fname in ("Solution.java", "notes.md", ".leetknight.json"):
        fpath = os.path.join(problem_dir, fname)
        if not os.path.exists(fpath):
            failures.append(f"{fname} was not created")
        elif os.path.getsize(fpath) == 0:
            failures.append(f"{fname} is empty")

    meta_path = os.path.join(problem_dir, ".leetknight.json")
    if os.path.exists(meta_path) and os.path.getsize(meta_path) > 0:
        try:
            with open(meta_path) as fh:
                meta = json.load(fh)
        except json.JSONDecodeError as e:
            failures.append(f".leetknight.json is not valid JSON: {e}")
        else:
            for key in REQUIRED_META_KEYS:
                value = meta.get(key)
                if value is None or (isinstance(value, str) and not value.strip()):
                    failures.append(f".leetknight.json is missing or empty key '{key}'")

    solution_path = os.path.join(problem_dir, "Solution.java")
    if os.path.exists(solution_path) and os.path.getsize(solution_path) > 0:
        with open(solution_path) as fh:
            src = fh.read()
        if "// Time:" not in src:
            failures.append(
                "Solution.java missing the injected `// Time:` header — "
                "inject_complexity_header regressed?"
            )
        if "class Solution" not in src:
            failures.append(
                "Solution.java missing `class Solution` — LeetCode codeSnippets "
                "field shape may have changed."
            )

    return failures


def main() -> int:
    project_root = os.getcwd()
    new_py = os.path.join(project_root, "scripts", "new.py")
    if not os.path.isfile(new_py):
        print(f"ERROR: cannot find scripts/new.py from cwd={project_root}", file=sys.stderr)
        return 2

    workspace = tempfile.mkdtemp(prefix="leetknight-canary-")
    try:
        shutil.copy(new_py, workspace)
        os.chmod(os.path.join(workspace, "new.py"), 0o755)

        print(f"=== Canary: {TARGET_URL} ===", flush=True)
        failures = run_canary(workspace)
        if failures:
            for f in failures:
                print(f"  FAIL  {f}", flush=True)
            gh_output = os.environ.get("GITHUB_OUTPUT")
            if gh_output:
                with open(gh_output, "a") as fh:
                    fh.write("failures<<EOF\n")
                    for f in failures:
                        fh.write(f"- {f}\n")
                    fh.write("EOF\n")
            print("\n--- Summary: FAILED ---")
            return 1

        print("  PASS")
        print("\n--- Summary: canary passed ---")
        return 0
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
