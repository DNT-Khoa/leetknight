<div align="center">
  <img src="media/icon.png" alt="leet.io" width="128"/>
  <h1>leet.io</h1>
  <p>Scaffold, test, and submit LeetCode problems in Java — with an Anki-inspired rating step that drives a hardest-first practice queue.</p>
</div>

> [!WARNING]
> **Under active development.** leet.io is pre-1.0. Commands, data-file schemas (`.leetio/reviews.json`, per-problem `.leetio.json`), and the rating workflow may change between versions without a migration path. Feedback and issue reports are welcome.

## What it does

leet.io is a VS Code extension for interview prep on LeetCode in Java. It:

- **Scaffolds problems locally** — pick from the LeetCode catalog (or paste a URL) and it creates `<slug>/Solution.java` with the official Java starter (plus a Time/Space complexity header) alongside `<slug>/notes.md` with the problem description.
- **Runs & submits from the editor** — ▶ runs your solution against LeetCode's own example test cases via the "Run Code" endpoint; ☁️ submits it for real. Both use LeetCode's `java` runtime — nothing is compiled locally.
- **Grades your recall** — after every Accepted submission, a modal asks you to rate the attempt (**Hard / Medium / Easy**). Ratings drive the practice panel: 🔴 Hard problems appear at the top, 🟢 Easy at the bottom. Within a group the oldest attempts come first so you don't see the same problem every session.
- **Re-solves on demand** — click any problem in the panel and it silently resets `Solution.java` back to the starter so you can re-solve it from scratch. The random-pick button picks one at random (interview-mode: no idea what's coming).

## Install

**Requirements**

- **Python 3.10+** on your PATH (`python3 --version` must work). The bundled helper scripts use it to talk to LeetCode's API.
- `pip install requests beautifulsoup4` — used by the bundled scripts.
- **VS Code 1.85+**.
- No local JDK required. LeetCode compiles and runs your submission on their servers.

Then in a new folder run **`leet.io: Initialize Workspace`** from the Command Palette to seed `.leetio/reviews.json`.

## LeetCode setup

Test/Submit hit LeetCode's authenticated endpoints, so leet.io needs your browser session cookies:

1. Log in to leetcode.com in your browser.
2. Open DevTools → Application → Cookies → `https://leetcode.com`.
3. Copy the values of `LEETCODE_SESSION` and `csrftoken`.
4. Run **`leet.io: Set LeetCode Cookies`** from the Command Palette and paste them (they're stored in VS Code's SecretStorage, backed by your OS keychain).

Cookies typically last ~2 weeks. When they expire you'll see an `[auth]` message telling you which one to refresh.

## Daily workflow

1. **Add a problem** — `leet.io: Search LeetCode` (or `New Problem from URL`). Picks land at `<workspace>/<slug>/` and the `Solution.java` auto-opens.
2. **Iterate** — click ▶ to run example cases. Fast, doesn't count as a submission, uses LeetCode's own judge.
3. **Submit** — click ☁️, confirm `y` in the terminal. On Accepted, a modal pops up: **How hard was this?** Pick Hard / Medium / Easy (dismissing defaults to Easy).
4. **Practice later** — open the **leet.io** activity-bar entry. Your solved problems are grouped by rating with hardest at the top. Click any row to re-solve (silent reset to starter). Or click the random-pick button for interview mode.
5. **Reset manually** — the ↻ button in the editor toolbar resets `Solution.java` back to the starter. Panel-click and random-pick do the same silently as part of opening the problem.

## Commands

| Command | What it does |
|---|---|
| `leet.io: Initialize Workspace` | Create `.leetio/reviews.json` in the current folder |
| `leet.io: Search LeetCode` | Fuzzy-search the catalog and scaffold the pick |
| `leet.io: New Problem from URL` | Scaffold a specific LeetCode URL |
| `leet.io: Run Tests` (▶) | Run example cases via `interpret_solution` |
| `leet.io: Submit` (☁️) | Real submission; opens Hard/Medium/Easy modal on Accepted |
| `leet.io: Reset Problem` (↻) | Reset `Solution.java` to the starter |
| `leet.io: Pick Random Practice Problem` | Open a random tracked problem for re-solving |
| `leet.io: Set LeetCode Cookies` | Paste `LEETCODE_SESSION` + `csrftoken` |

## How it works

- Every problem you scaffold gets a hidden `<slug>/.leetio.json` cache containing the LeetCode `questionId`, `exampleTestcases`, and the original `initialCode`. This means Run / Submit / Reset don't need to re-hit LeetCode's rate-limited GraphQL endpoint on every invocation.
- Ratings and attempt history live in a single `<workspace>/.leetio/reviews.json` — human-readable, git-committable, portable between machines. This is populated organically as you submit; there is no bulk history import.
- Communication between the Submit script and the VS Code extension happens via `<workspace>/.leetio/pending.json`: the Python script writes it on Accepted, the extension tails it with a `FileSystemWatcher`, pops the rating modal, and deletes the file.
- Language is fixed to Java. Every problem is scaffolded from LeetCode's `java` code snippet, and Run/Submit send `"lang": "java"` to the judge.

## License

MIT
