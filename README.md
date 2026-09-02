<div align="center">
  <img src="https://raw.githubusercontent.com/DNT-Khoa/leetknight/main/media/icon.png" alt="LeetKnight" width="128"/>
  <h1>LeetKnight</h1>
  <p>Scaffold, test, and submit LeetCode problems in Java — with an Anki-inspired rating step that drives a hardest-first practice queue.</p>
</div>

> [!WARNING]
> **Under active development.** LeetKnight is pre-1.0. Commands, data-file schemas (`.leetknight/reviews.json`, per-problem `.leetknight.json`), and the rating workflow may change between versions without a migration path. Feedback and issue reports are welcome.

## What it does

LeetKnight is a VS Code extension for interview prep on LeetCode in Java. It:

- **Scaffolds problems locally** — pick from the LeetCode catalog (or paste a URL) and it creates `<slug>/Solution.java` with the official Java starter (plus a Time/Space complexity header) alongside `<slug>/notes.md` with the problem description.
- **Runs & submits from the editor** — ▶ runs your solution against LeetCode's own example test cases via the "Run Code" endpoint; ☁️ submits it for real. Both use LeetCode's `java` runtime — nothing is compiled locally.
- **Grades your recall** — after every Accepted submission, a modal asks you to rate the attempt (**Hard / Medium / Easy**). Ratings drive the practice panel, grouped 🔴 Hard → 🟡 Medium → 🟢 Easy so the ones you found hardest sit at the top. Within a group the oldest attempts come first so you don't see the same problem every session.
- **Re-solves on demand** — click any problem in the panel and it opens `Solution.java` and resets it back to the starter (no confirmation prompt) so you can re-solve it from scratch. The random-pick button picks one at random (interview-mode: no idea what's coming).

## Install

**Requirements**

- **Python 3.10+** on your PATH (`python3 --version` must work). The bundled helper scripts use it to talk to LeetCode's API.
- `pip install requests beautifulsoup4` — used by the bundled scripts.
- **VS Code 1.85+**.
- No local JDK required. LeetCode compiles and runs your submission on their servers.

Then in a new folder run **`LeetKnight: Initialize Workspace`** from the Command Palette to seed `.leetknight/reviews.json`.

## LeetCode setup

Test/Submit hit LeetCode's authenticated endpoints, so LeetKnight needs your browser session cookies:

1. Log in to leetcode.com in your browser.
2. Open DevTools → Application → Cookies → `https://leetcode.com`.
3. Copy the values of `LEETCODE_SESSION` and `csrftoken`.
4. Run **`LeetKnight: Set LeetCode Cookies`** from the Command Palette and paste them (they're stored in VS Code's SecretStorage, backed by your OS keychain).

Cookies typically last ~2 weeks. When they expire you'll see an `[auth]` message telling you which one to refresh.

## Daily workflow

1. **Add a problem** — `LeetKnight: Search LeetCode` (or `New Problem from URL`). Picks land at `<workspace>/<slug>/` and the `Solution.java` auto-opens.
2. **Iterate** — click ▶ to run example cases. Fast, doesn't count as a submission, uses LeetCode's own judge.
3. **Submit** — click ☁️, confirm `y` in the terminal. On Accepted, a modal pops up: **How hard was this?** Pick Hard / Medium / Easy (dismissing defaults to Easy).
4. **Practice later** — open the **LeetKnight** activity-bar entry. Your solved problems are grouped by rating with hardest at the top. Click any row to re-solve — it opens the file and resets to the starter in one step. Or click the random-pick button for interview mode.
5. **Reset manually** — the ↻ button in the editor toolbar resets `Solution.java` back to the starter. Panel-click and random-pick do the same as part of opening the problem, so you don't need to reset separately.

## Commands

| Command | What it does |
|---|---|
| `LeetKnight: Initialize Workspace` | Create `.leetknight/reviews.json` in the current folder |
| `LeetKnight: Search LeetCode` | Fuzzy-search the catalog and scaffold the pick |
| `LeetKnight: New Problem from URL` | Scaffold a specific LeetCode URL |
| `LeetKnight: Run Tests` (▶) | Run example cases via `interpret_solution` |
| `LeetKnight: Submit` (☁️) | Real submission; opens Hard/Medium/Easy modal on Accepted |
| `LeetKnight: Reset Problem` (↻) | Reset `Solution.java` to the starter |
| `LeetKnight: Pick Random Practice Problem` | Open a random tracked problem for re-solving |
| `LeetKnight: Set LeetCode Cookies` | Paste `LEETCODE_SESSION` + `csrftoken` |

## How it works

- Every problem you scaffold gets a hidden `<slug>/.leetknight.json` cache containing the LeetCode `questionId`, `exampleTestcases`, and the original `initialCode`. This means Run / Submit / Reset don't need to re-hit LeetCode's rate-limited GraphQL endpoint on every invocation.
- Ratings and attempt history live in a single `<workspace>/.leetknight/reviews.json` — human-readable, git-committable, portable between machines. This is populated organically as you submit; there is no bulk history import.
- Communication between the Submit script and the VS Code extension happens via `<workspace>/.leetknight/pending.json`: the Python script writes it on Accepted, the extension tails it with a `FileSystemWatcher`, pops the rating modal, and deletes the file.
- Language is fixed to Java. Every problem is scaffolded from LeetCode's `java` code snippet, and Run/Submit send `"lang": "java"` to the judge.

## License

MIT
