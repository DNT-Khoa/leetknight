# Changelog

## 1.0.0

- Add `playground/Playground.java` scratch pad and a `LeetKnight: Run Playground` command (▶ in the editor toolbar) that compiles and runs it locally via `javac`/`java`. Scaffolded during `Initialize Workspace`; `Run Playground` self-heals a missing folder so existing workspaces don't need to re-init.

## 0.1.0

Initial release.

- Scaffold LeetCode problems from a search picker or URL into `<slug>/Solution.java` + `<slug>/notes.md`.
- Run example test cases and submit against LeetCode's authenticated endpoints from the editor toolbar (Java only).
- Rate accepted submissions (Hard / Medium / Easy) to drive a practice panel that surfaces the hardest problems first.
- Re-solve any tracked problem by click (silent reset) or use the random-pick button for interview-mode practice.
- Credentials stored in VS Code's SecretStorage (OS keychain).
