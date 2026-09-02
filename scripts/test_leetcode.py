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


def split_cases(example_testcases: str, code_answers: list) -> list[str]:
    """Split LeetCode's raw exampleTestcases into per-case display strings.

    LeetCode returns example inputs as one big newline-separated block, one
    parameter per line, with N params per case. We know how many cases there
    are because the judge returns exactly len(cases) `code_answer` entries.
    """
    if not example_testcases:
        return []
    lines = example_testcases.split("\n")
    n_cases = max(1, len(code_answers))
    if n_cases == 0 or len(lines) % n_cases != 0:
        return [example_testcases]
    per_case = len(lines) // n_cases
    return ["\n".join(lines[i * per_case:(i + 1) * per_case]) for i in range(n_cases)]


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

    status_msg = result.get("status_msg", "?")
    compile_err = (result.get("compile_error") or "").strip()
    runtime_err = (result.get("runtime_error") or "").strip()
    your = result.get("code_answer") or []
    expect = result.get("expected_code_answer") or []
    stdout_per_case = result.get("code_output") or []
    compare_result = result.get("compare_result") or ""

    print()
    print(f"Judge status: {status_msg}  ({elapsed:.2f}s)")

    if compile_err:
        print()
        print("Compile error:")
        print(compile_err)
        return 1

    if runtime_err:
        print()
        print("Runtime error:")
        print(runtime_err)

    inputs_per_case = split_cases(data_input, your or expect or [""])
    pass_count = 0
    fail_count = 0
    for i in range(max(len(your), len(expect))):
        y = your[i].strip() if i < len(your) else ""
        e = expect[i].strip() if i < len(expect) else ""
        if not y and not e:
            continue
        bit = compare_result[i] if i < len(compare_result) else None
        ok, note = grade_case(y, e, bit)
        mark = "PASS" if ok else "FAIL"
        if ok:
            pass_count += 1
        else:
            fail_count += 1
        print(f"\nTest {i + 1}: {mark}{note}")
        if i < len(inputs_per_case):
            print(f"  input:    {inputs_per_case[i]!r}")
        print(f"  your:     {y}")
        print(f"  expected: {e}")
        if i < len(stdout_per_case) and stdout_per_case[i]:
            print(f"  stdout:   {stdout_per_case[i]}")

    print()
    print(f"Summary: {pass_count} passed, {fail_count} failed")
    return 0 if fail_count == 0 and not runtime_err else 1


if __name__ == "__main__":
    sys.exit(main())
