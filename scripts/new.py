#!/usr/bin/env python3
"""
Scaffold a new LeetCode problem into <workspace>/<slug>/.

Usage:
  ./new.py <problem-url>

Example:
  ./new.py https://leetcode.com/problems/two-sum/

Writes:
  <slug>/Solution.java     Java starter code + Time/Space complexity header
  <slug>/notes.md          Title + problem link + description (plain markdown)
  <slug>/.leetio.json      { title, difficulty, questionId, url,
                             exampleTestcases, initialCode } — metadata read
                             by test_leetcode.py, submit_leetcode.py, and
                             reset_problem.py so they don't need to re-fetch
                             from LeetCode on every run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

HTTP_TIMEOUT_SECONDS = 25
TRANSIENT_EXC_NAMES = {"Timeout", "ReadTimeout", "ConnectTimeout", "ConnectionError"}

WORKSPACE = os.getcwd()
GRAPHQL = "https://leetcode.com/graphql/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.5",
    "Content-Type": "application/json",
}

COMPLEXITY_HEADER = "// Time:  O(?)\n// Space: O(?)\n\n"


def inject_complexity_header(code: str) -> str:
    """Insert COMPLEXITY_HEADER directly above the `class Solution` line.

    Placing it adjacent to the class (rather than at the top of the file)
    keeps any LeetCode-provided preface intact — most commonly the
    `Definition for singly-linked list.` block for linked-list problems and
    the equivalent `TreeNode` block for tree problems.

    Fallback: if no `class Solution` line exists (a handful of LeetCode
    problems ship a function-only starter or a different top-level class),
    prepend to the top of the file.

    De-dupe: if a `// Time:` line already exists in the snippet, skip
    injection entirely.
    """
    if re.search(r"^\s*//\s*Time\s*:", code, re.MULTILINE):
        return code
    pattern = re.compile(r"^(\s*class\s+Solution\b)", re.MULTILINE)
    m = pattern.search(code)
    if not m:
        return COMPLEXITY_HEADER + code
    return code[:m.start()] + COMPLEXITY_HEADER + code[m.start():]


def slug_from_url(url: str) -> str:
    m = re.search(r"/problems/([^/?#]+)", url)
    if not m:
        raise ValueError(f"could not extract slug from URL: {url}")
    return m.group(1)


def fetch_question(slug: str, url: str) -> dict:
    """GraphQL questionData → { title, difficulty, questionId, content,
    exampleTestcases, javaSnippet }."""
    import requests

    query = """
    query questionData($titleSlug: String!) {
      question(titleSlug: $titleSlug) {
        questionId
        title
        difficulty
        content
        exampleTestcases
        codeSnippets { langSlug code }
      }
    }
    """
    r = requests.post(
        GRAPHQL,
        json={
            "operationName": "questionData",
            "variables": {"titleSlug": slug},
            "query": query,
        },
        headers={**HEADERS, "Referer": url},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    r.raise_for_status()
    question = (r.json().get("data") or {}).get("question")
    if not question:
        raise ValueError(
            f"no public problem found for slug '{slug}' (premium-only?). "
            "leet.io cannot scaffold premium problems — they require a paid subscription."
        )

    java_snippet = None
    for snip in question.get("codeSnippets") or []:
        if snip.get("langSlug") == "java":
            java_snippet = snip.get("code")
            break
    if not java_snippet:
        raise ValueError(
            f"no java code snippet for '{slug}' — this problem may only "
            "support other languages."
        )

    return {
        "questionId": question.get("questionId") or "",
        "title": question.get("title") or slug,
        "difficulty": question.get("difficulty") or "Unknown",
        "content": question.get("content") or "",
        "exampleTestcases": question.get("exampleTestcases") or "",
        "javaSnippet": java_snippet,
    }


def fetch_with_retry(slug: str, url: str) -> dict:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            return fetch_question(slug, url)
        except Exception as e:
            last_exc = e
            if type(e).__name__ not in TRANSIENT_EXC_NAMES or attempt == 2:
                raise
            wait = 2 * (attempt + 1)
            print(f"Warning: fetch attempt {attempt + 1} failed ({e}); retrying in {wait}s...")
            time.sleep(wait)
    raise last_exc  # unreachable but keeps type checker happy


def html_to_markdown(content_html: str) -> str:
    """Convert LeetCode's problem description HTML into plain markdown."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(content_html, "html.parser")
    lines: list[str] = []
    for el in soup.find_all(["p", "li", "pre"]):
        if el.name == "pre":
            text = el.get_text("\n").strip()
            if text:
                lines.append("```\n" + text + "\n```")
        elif el.name == "p":
            text = el.get_text(" ", strip=True)
            if text:
                lines.append(text)
        elif el.name == "li":
            text = el.get_text(" ", strip=True)
            if text:
                lines.append(f"- {text}")
    return "\n\n".join(lines)


def scaffold(url: str) -> None:
    slug = slug_from_url(url)
    problem_dir = os.path.join(WORKSPACE, slug)

    if os.path.isdir(problem_dir):
        print(f"Already exists: {problem_dir}")
        sys.exit(1)

    print(f"Fetching '{slug}' from LeetCode...", flush=True)
    q = fetch_with_retry(slug, url)

    os.makedirs(problem_dir)

    initial_code = inject_complexity_header(q["javaSnippet"])
    if not initial_code.endswith("\n"):
        initial_code += "\n"

    solution_path = os.path.join(problem_dir, "Solution.java")
    with open(solution_path, "w") as f:
        f.write(initial_code)
    print(f"Created: {solution_path}")

    notes_path = os.path.join(problem_dir, "notes.md")
    description = html_to_markdown(q["content"])
    with open(notes_path, "w") as f:
        f.write(f"# {q['title']}\n\n")
        f.write(f"**Difficulty:** {q['difficulty']}  \n")
        f.write(f"**Link:** {url}\n\n")
        if description:
            f.write("---\n\n")
            f.write(description)
            f.write("\n")
    print(f"Created: {notes_path}")

    meta = {
        "slug": slug,
        "title": q["title"],
        "difficulty": q["difficulty"],
        "questionId": q["questionId"],
        "url": url,
        "exampleTestcases": q["exampleTestcases"],
        "initialCode": initial_code,
    }
    meta_path = os.path.join(problem_dir, ".leetio.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"Created: {meta_path}")

    print(f"\nNext: open {os.path.join(slug, 'Solution.java')} and click the ▶ button in the editor toolbar to run tests.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="new.py",
        description="Scaffold a new LeetCode problem (Java).",
        usage="./new.py <problem-url>",
    )
    parser.add_argument("url", help="full LeetCode problem URL")
    args = parser.parse_args()

    if not args.url.startswith(("http://", "https://")):
        parser.error("expected a full URL (e.g. https://leetcode.com/problems/two-sum/)")

    try:
        scaffold(args.url)
    except ValueError as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
