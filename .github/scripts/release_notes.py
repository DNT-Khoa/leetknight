#!/usr/bin/env python3
"""
Generate AI-curated release notes for a new LeetKnight release.

Usage:
    python3 scripts/release_notes.py <prev_tag_or_empty> <version>

Reads commit log + file stats between <prev_tag> and HEAD, asks Claude to
produce structured markdown release notes, and prints them to stdout.

Reads ANTHROPIC_API_KEY from the environment.

Exits non-zero on any failure so the workflow can fall back to a plain
git-log changelog without breaking the release.
"""

from __future__ import annotations

import os
import subprocess
import sys

PROMPT_TEMPLATE = """You are writing release notes for a VS Code extension called LeetKnight.

LeetKnight helps interview prep on LeetCode in Java. It scaffolds Java solutions from the LeetCode catalog (each problem gets its own folder with `Solution.java`, `notes.md`, and a hidden `.leetknight.json` cache), runs example tests via LeetCode's own judge, submits real solutions, and — after each Accepted submit — pops a modal asking the user to rate the attempt Hard / Medium / Easy. Those ratings drive a "Practice" sidebar panel that groups solved problems into 🔴 Hard / 🟡 Medium / 🟢 Easy tiers so the hardest ones bubble to the top for re-solving. Clicking a problem in the panel opens `Solution.java` and resets it back to the starter (no confirmation prompt) so the user re-solves from scratch; a random-pick button picks one at random for interview-style surprise. Auth is via `LEETCODE_SESSION` + `csrftoken` browser cookies stored in VS Code SecretStorage.

Generate concise, well-structured release notes for version {version}, based on the commits and changed files below.

Rules:
- Group changes into sections with emoji headers — only include sections that have actual changes. Pick from: ✨ Features, 🐛 Fixes, 📝 Documentation, 🔧 CI / Tooling, ♻️ Refactor, ⚡ Performance.
- Each bullet should explain WHAT changed and WHY it matters to the user — 1-2 sentences. Don't just restate the commit message verbatim.
- Skip trivial commits (typo fixes, lockfile bumps, formatting-only) unless they're meaningful.
- Always skip the `chore: release vX.Y.Z` commit — that's the automated version bump and contains no real changes.
- Do NOT invent metrics, numbers, or rationale that aren't visible in the commit log or diff stats. If a commit doesn't explain why, write a plausible user-facing impact based on the file paths involved.
- Start the output directly with the first section header. No preamble like "This release..." or "Hello!".
- Do NOT include an Install section — the workflow prepends one automatically.

Commits since {prev_tag_label}:
```
{commits}
```

Files changed:
```
{file_stats}
```

Output the markdown release notes now:
"""


def run(args: list[str]) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: release_notes.py <prev_tag_or_empty> <version>", file=sys.stderr)
        return 2

    prev_tag, version = sys.argv[1], sys.argv[2]

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 3

    rng = f"{prev_tag}..HEAD" if prev_tag else "HEAD"

    commits = run(["git", "log", rng, "--pretty=format:- %s%n%b", "--no-merges"]).strip()
    file_stats = run(["git", "diff", "--stat", rng]).strip() if prev_tag else ""

    if not commits:
        print("(no changes since previous release)")
        return 0

    prompt = PROMPT_TEMPLATE.format(
        version=version,
        prev_tag_label=prev_tag or "the initial release",
        commits=commits,
        file_stats=file_stats or "(initial release; no diff stats)",
    )

    try:
        from anthropic import Anthropic
    except ImportError:
        print("anthropic package not installed", file=sys.stderr)
        return 4

    client = Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    text = "".join(block.text for block in msg.content if block.type == "text").strip()
    if not text:
        print("Claude returned an empty response", file=sys.stderr)
        return 5

    print(text)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        print(f"git failed: {e.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"release_notes failed: {e}", file=sys.stderr)
        sys.exit(1)
