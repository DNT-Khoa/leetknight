#!/usr/bin/env python3
"""
Submit a LeetCode Solution.java as an official judged submission.

Unlike test_leetcode.py (which uses interpret_solution and does NOT count),
this hits the /submit/ endpoint — the submission shows up in your LeetCode
submission history and counts toward acceptance rate.

On Accepted, writes <workspace>/.leetknight/pending.json with the problem's
{slug, title, difficulty, url, at}. The VS Code extension tails this file
with a FileSystemWatcher and, when it appears, pops the Hard/Medium/Easy
rating modal and merges the entry into reviews.json.

Usage:
  ./submit_leetcode.py <problem-slug>

Expects LEETCODE_SESSION and LEETCODE_CSRF in env.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time

import leetcode_auth as auth

BASE = "https://leetcode.com"
POLL_INTERVAL = 1.0
POLL_MAX_WAIT = 60


def load_meta(problem_dir: str) -> dict:
    meta_path = os.path.join(problem_dir, ".leetknight.json")
    if not os.path.isfile(meta_path):
        raise FileNotFoundError(
            f"missing {meta_path}. Re-scaffold with 'LeetKnight: New Problem'."
        )
    with open(meta_path) as fh:
        return json.load(fh)


def submit(session, slug: str, question_id: str, code: str) -> dict:
    r = session.post(
        f"{BASE}/problems/{slug}/submit/",
        json={
            "lang": "java",
            "question_id": question_id,
            "typed_code": code,
        },
        timeout=auth.HTTP_TIMEOUT_SECONDS,
    )
    if r.status_code != 200:
        raise auth.classify_response_error(r.status_code, r.text, r.headers.get("Retry-After"))
    body = r.json()
    submission_id = body.get("submission_id")
    if not submission_id:
        raise auth.AuthError(f"no submission_id in response: {r.text[:200]}", reason="other")

    deadline = time.time() + POLL_MAX_WAIT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        cr = session.get(
            f"{BASE}/submissions/detail/{submission_id}/check/",
            timeout=auth.HTTP_TIMEOUT_SECONDS,
        )
        if cr.status_code != 200:
            raise auth.classify_response_error(cr.status_code, cr.text, cr.headers.get("Retry-After"))
        data = cr.json()
        if data.get("state") == "SUCCESS":
            data["_submission_id"] = submission_id
            return data
    raise auth.AuthError(f"timed out waiting for verdict after {POLL_MAX_WAIT}s", reason="other")


def confirm(slug: str) -> bool:
    print(f"About to submit Solution.java to LeetCode problem '{slug}'.")
    print("This counts as an official submission and affects your acceptance rate.")
    try:
        ans = input("Submit? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return ans in ("y", "yes")


def write_pending(workspace: str, meta: dict) -> None:
    """Signal the extension that a submission just landed as Accepted."""
    pending_dir = os.path.join(workspace, ".leetknight")
    os.makedirs(pending_dir, exist_ok=True)
    payload = {
        "slug": meta["slug"],
        "title": meta.get("title") or meta["slug"],
        "difficulty": meta.get("difficulty") or "Unknown",
        "url": meta.get("url") or f"https://leetcode.com/problems/{meta['slug']}/",
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    tmp_path = os.path.join(pending_dir, "pending.json.tmp")
    final_path = os.path.join(pending_dir, "pending.json")
    with open(tmp_path, "w") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp_path, final_path)


def main() -> int:
    ap = argparse.ArgumentParser(description="Submit a LeetCode Solution.java for official judging.")
    ap.add_argument("problem", help="LeetCode problem slug (the folder name)")
    ap.add_argument("--yes", action="store_true", help="skip confirmation prompt")
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

    question_id = meta.get("questionId") or ""
    if not question_id:
        print(f"[error] no questionId in .leetknight.json — re-scaffold this problem.", file=sys.stderr)
        return 1

    with open(solution_path) as fh:
        code = fh.read()

    if not args.yes and not confirm(args.problem):
        print("Cancelled.")
        return 0

    try:
        sess_info = auth.load_session_from_env()
    except auth.AuthError as e:
        auth.fail(e)

    session = auth.make_requests_session(sess_info, referer_path=f"/problems/{args.problem}/")

    print("Submitting...", flush=True)
    t0 = time.time()
    try:
        result = submit(session, args.problem, question_id, code)
    except auth.AuthError as e:
        auth.fail(e)
    elapsed = time.time() - t0

    status_msg = result.get("status_msg", "?")
    submission_id = result.get("_submission_id")
    print()
    print(f"Verdict: {status_msg}  ({elapsed:.1f}s)")
    print(f"Submission: {BASE}/submissions/detail/{submission_id}/")

    if status_msg == "Accepted":
        runtime = result.get("status_runtime", "?")
        memory = result.get("status_memory", "?")
        runtime_pct = result.get("runtime_percentile")
        memory_pct = result.get("memory_percentile")
        print(f"  Runtime: {runtime}" + (f"  (beats {runtime_pct:.1f}%)" if runtime_pct is not None else ""))
        print(f"  Memory:  {memory}" + (f"  (beats {memory_pct:.1f}%)" if memory_pct is not None else ""))
        try:
            write_pending(workspace, meta)
        except Exception as e:
            print(f"[warn] could not write pending.json for LeetKnight rating modal: {e}", file=sys.stderr)
        return 0

    if (result.get("compile_error") or "").strip():
        print()
        print("Compile error:")
        print(result["compile_error"])
        return 1

    if (result.get("runtime_error") or "").strip():
        print()
        print("Runtime error:")
        print(result["runtime_error"])

    last_input = result.get("last_testcase") or result.get("input")
    expected = result.get("expected_output")
    your = result.get("code_output")
    if last_input is not None:
        print()
        print("Failing case:")
        print(f"  input:    {last_input!r}")
        if expected is not None:
            print(f"  expected: {expected}")
        if your is not None:
            print(f"  got:      {your}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
