#!/usr/bin/env python3
"""
Run a LeetCode Solution.java against its example test cases via LeetCode's own
judge (the "Run Code" endpoint from the LeetCode web IDE).

Reads exampleTestcases from <slug>/.leetknight.json — cached at scaffold time,
so no extra GraphQL round trip on every run.

Rate-limit note
---------------
LeetCode rate-limits this endpoint hard (~1 request per few seconds per
account). We concatenate all example cases into one data_input and send ONE
request. The judge runs all cases in the same container and returns parallel
code_answer / expected_code_answer arrays.

Per-case rendering
------------------
- Sample case (LeetCode supplies expected): PASS/FAIL, using the judge's
  per-case bitmap `compare_result` — this correctly handles multi-valid-answer
  problems (e.g. two-sum returning [1,0] vs [0,1]) where string equality would
  falsely flag FAIL.

Usage:
  ./test_leetcode.py <problem-slug>

The script expects LEETCODE_SESSION and LEETCODE_CSRF in env.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import leetcode_auth as auth

BASE = "https://leetcode.com"
POLL_INTERVAL = 0.5
POLL_MAX_WAIT = 30


def grade_case(your: str, expected: str, compare_bit: str | None) -> tuple[bool, str]:
    """Per-case verdict.

    compare_bit is the judge's per-case mark from `compare_result`: "1" means
    the judge accepted that case (including multi-valid-answer problems where
    `your` and `expected` differ as strings), "0" means it rejected it. When
    the bitmap is unavailable for this index, fall back to string equality.
    """
    if compare_bit is not None:
        ok = compare_bit == "1"
    else:
        ok = your == expected
    note = "  (judge accepted equivalent answer)" if ok and your != expected else ""
    return ok, note


def load_meta(problem_dir: str) -> dict:
    meta_path = os.path.join(problem_dir, ".leetknight.json")
    if not os.path.isfile(meta_path):
        raise FileNotFoundError(
            f"missing {meta_path}. Re-scaffold with 'LeetKnight: New Problem'."
        )
    with open(meta_path) as fh:
        return json.load(fh)


def run_batch(session, slug: str, question_id: str, code: str, data_input: str) -> dict:
    r = session.post(
        f"{BASE}/problems/{slug}/interpret_solution/",
        json={
            "lang": "java",
            "question_id": question_id,
            "typed_code": code,
            "data_input": data_input,
        },
        timeout=auth.HTTP_TIMEOUT_SECONDS,
    )
    if r.status_code != 200:
        raise auth.classify_response_error(r.status_code, r.text, r.headers.get("Retry-After"))
    interpret_id = r.json().get("interpret_id")
    if not interpret_id:
        raise auth.AuthError(f"no interpret_id in response: {r.text[:200]}", reason="other")

    deadline = time.time() + POLL_MAX_WAIT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        cr = session.get(
            f"{BASE}/submissions/detail/{interpret_id}/check/",
            timeout=auth.HTTP_TIMEOUT_SECONDS,
        )
        if cr.status_code != 200:
            raise auth.classify_response_error(cr.status_code, cr.text, cr.headers.get("Retry-After"))
        data = cr.json()
        if data.get("state") == "SUCCESS":
            return data
    raise auth.AuthError(f"timed out waiting for judge after {POLL_MAX_WAIT}s", reason="other")


def split_cases(example_testcases: str, code_answers: list, n_params: int = 0) -> list[str]:
    """Split LeetCode's raw exampleTestcases into per-case display strings.

    LeetCode returns example inputs as one big newline-separated block, one
    parameter per line, with N params per case. When the method's parameter
    count is known, that decides the split. Otherwise fall back to the number
    of answers the judge returned, which is less reliable: the judge's answer
    lists can carry a trailing empty entry, or stop early on a runtime error.
    """
    if not example_testcases:
        return []
    lines = example_testcases.split("\n")
    if n_params > 0 and len(lines) % n_params == 0:
        return ["\n".join(lines[i:i + n_params]) for i in range(0, len(lines), n_params)]
    n_cases = max(1, len(code_answers))
    if n_cases == 0 or len(lines) % n_cases != 0:
        return [example_testcases]
    per_case = len(lines) // n_cases
    return ["\n".join(lines[i * per_case:(i + 1) * per_case]) for i in range(n_cases)]


def split_top_level(s: str, sep: str = ",") -> list[str]:
    """Split on `sep`, ignoring separators nested inside <...> generics."""
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


def param_names(initial_code: str) -> list[str]:
    """Parameter names of the first public method in the Java stub.

    e.g. `public int[] twoSum(int[] nums, int target)` -> ["nums", "target"].
    Returns [] if no method is found, or for design problems (no `class
    Solution`), whose input is an op list + arg list rather than one line per
    method parameter.
    """
    if "class Solution" not in (initial_code or ""):
        return []
    m = re.search(r"public\s+[\w<>\[\],\s]+?\s+\w+\s*\(([^)]*)\)", initial_code or "")
    if not m:
        return []
    names = []
    for p in split_top_level(m.group(1)):
        tokens = p.strip().split()
        if tokens:
            names.append(tokens[-1])
    return names


def format_input(case_input: str, names: list[str]) -> list[str]:
    """One line per argument, labelled with its parameter name when the
    number of lines matches the method signature."""
    lines = case_input.split("\n")
    if len(names) != len(lines):
        return lines
    width = max(len(n) for n in names)
    return [f"{n.ljust(width)} = {v}" for n, v in zip(names, lines)]


def render(result: dict, data_input: str, names: list[str], elapsed: float) -> tuple[list[str], int]:
    """Turn a judge result into console lines and an exit code."""
    status_msg = result.get("status_msg", "?")
    compile_err = (result.get("compile_error") or "").strip()
    runtime_err = (result.get("runtime_error") or "").strip()
    your = result.get("code_answer") or []
    expect = result.get("expected_code_answer") or []
    stdout_per_case = result.get("code_output") or []
    compare_result = result.get("compare_result") or ""
    timing = f"({elapsed:.2f}s)"

    if compile_err:
        return [f"❌ Compile error  {timing}", "", compile_err], 1

    # The judge's answer lists can end with an empty entry that isn't a case.
    while expect and not expect[-1].strip():
        expect = expect[:-1]
    while your and len(your) > len(expect) and not your[-1].strip():
        your = your[:-1]

    inputs_per_case = split_cases(data_input, expect or your or [""], len(names))
    if names and len(inputs_per_case) > 1:
        n_cases = len(inputs_per_case)
    else:
        n_cases = max(len(your), len(expect))

    # With a runtime error the judge stops at the crashing case, so the first
    # case without an answer is the one that crashed and later ones never ran.
    crashed = None
    if runtime_err:
        crashed = next((i for i in range(n_cases) if i >= len(your) or not your[i].strip()), None)

    rows = []  # (index, status, your, expected); status in pass/fail/crash/skip
    for i in range(n_cases):
        y = your[i].strip() if i < len(your) else ""
        e = expect[i].strip() if i < len(expect) else ""
        if crashed is not None and i == crashed:
            rows.append((i, "crash", y, e))
        elif crashed is not None and i > crashed:
            rows.append((i, "skip", y, e))
        elif not y and not e:
            continue
        else:
            bit = compare_result[i] if i < len(compare_result) else None
            ok, _ = grade_case(y, e, bit)
            rows.append((i, "pass" if ok else "fail", y, e))

    total = len(rows)
    passed = sum(1 for r in rows if r[1] == "pass")
    failed = total - passed

    if crashed is not None:
        verdict = f"❌ Runtime error in test {crashed + 1}  {timing}"
    elif runtime_err:
        verdict = f"❌ Runtime error  {timing}"
    elif status_msg not in ("Accepted", "Runtime Error", "?"):
        # e.g. Time Limit Exceeded: the judge gave up, so if it produced no
        # answers at all, per-test "(no output)" rows would just be noise.
        if not any(y for _, _, y, _ in rows):
            return [f"❌ {status_msg}  {timing}"], 1
        verdict = f"❌ {status_msg}  {timing}"
    elif failed == 0 and total > 0:
        verdict = f"✅ All {total} {'test' if total == 1 else 'tests'} passed  {timing}"
    else:
        verdict = f"❌ {failed} of {total} {'test' if total == 1 else 'tests'} failed  {timing}"

    out = [verdict, ""]
    if runtime_err and crashed is None:
        out += ["Runtime error:", runtime_err, ""]

    icons = {"pass": "✅", "fail": "❌", "crash": "💥", "skip": "⏭️ "}
    labels = {"crash": "  runtime error", "skip": "  not run"}
    for i, status, y, e in rows:
        out.append(f"{icons[status]} Test {i + 1}{labels.get(status, '')}")
        if status in ("pass", "skip"):
            continue
        case_input = inputs_per_case[i] if i < len(inputs_per_case) else ""
        for j, line in enumerate(format_input(case_input, names)):
            out.append(f"     {'input' if j == 0 else '':<9} {line}")
        if status == "crash":
            for j, line in enumerate(runtime_err.splitlines()):
                out.append(f"     {'error' if j == 0 else '':<9} {line}")
        else:
            out.append(f"     {'your':<9} {y or '(no output)'}")
            out.append(f"     {'expected':<9} {e}")
        if i < len(stdout_per_case) and stdout_per_case[i]:
            stdout_lines = str(stdout_per_case[i]).rstrip("\n").splitlines()
            for j, line in enumerate(stdout_lines):
                out.append(f"     {'stdout' if j == 0 else '':<9} {line}")

    code = 0 if failed == 0 and total > 0 and not runtime_err else 1
    return out, code


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a LeetCode Solution.java via the official judge.")
    ap.add_argument("problem", help="LeetCode problem slug (the folder name)")
    args = ap.parse_args()

    workspace = os.getcwd()
    problem_dir = os.path.join(workspace, args.problem)
    solution_path = os.path.join(problem_dir, "Solution.java")

    if not os.path.isfile(solution_path):
        print(f"Not found: {solution_path}", file=sys.stderr)
        return 1

    try:
        meta = load_meta(problem_dir)
    except FileNotFoundError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1

    with open(solution_path) as fh:
        code = fh.read()

    data_input = meta.get("exampleTestcases") or ""
    if not data_input.strip():
        print(f"[error] no exampleTestcases in .leetknight.json — re-scaffold this problem.", file=sys.stderr)
        return 1
    question_id = meta.get("questionId") or ""
    if not question_id:
        print(f"[error] no questionId in .leetknight.json — re-scaffold this problem.", file=sys.stderr)
        return 1

    try:
        sess_info = auth.load_session_from_env()
    except auth.AuthError as e:
        auth.fail(e)

    session = auth.make_requests_session(sess_info, referer_path=f"/problems/{args.problem}/")

    print(f"Running example cases for '{args.problem}' via LeetCode judge...", flush=True)
    t0 = time.time()
    try:
        result = run_batch(session, args.problem, question_id, code, data_input)
    except auth.AuthError as e:
        auth.fail(e)
    elapsed = time.time() - t0

    lines, exit_code = render(result, data_input, param_names(meta.get("initialCode") or ""), elapsed)
    print()
    print("\n".join(lines))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
