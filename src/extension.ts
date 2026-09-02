import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import * as child_process from "child_process";
import { runInTerminal } from "./runner";
import { PracticeProvider } from "./practiceProvider";
import {
  reviewsPath,
  saveReviews,
  setRating,
  upsertOnSubmit,
  randomTrackedSlug,
  getEntry,
  PendingEntry,
  Rating,
} from "./reviews";

let extensionRoot: string;
let extensionContext: vscode.ExtensionContext;

const LEETCODE_SESSION_KEY = "leetknight.leetcodeSession";
const LEETCODE_CSRF_KEY = "leetknight.leetcodeCsrf";

const SOLUTION_FILENAME = "Solution.java";
const META_FILENAME = ".leetknight.json";

export function activate(context: vscode.ExtensionContext) {
  extensionRoot = context.extensionPath;
  extensionContext = context;

  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  const practice = new PracticeProvider(root);

  context.subscriptions.push(
    vscode.commands.registerCommand("leetknight.init", () => initWorkspace()),
    vscode.commands.registerCommand("leetknight.newProblem", () => newProblem()),
    vscode.commands.registerCommand("leetknight.searchLeetcode", () =>
      searchLeetcode(),
    ),
    vscode.commands.registerCommand("leetknight.runTests", () => runTests()),
    vscode.commands.registerCommand("leetknight.submit", () => submit()),
    vscode.commands.registerCommand("leetknight.resetProblem", () =>
      resetProblem(),
    ),
    vscode.commands.registerCommand("leetknight.pickRandom", () =>
      pickRandom(practice),
    ),
    vscode.commands.registerCommand("leetknight.setLeetcodeCookies", () =>
      setLeetcodeCookies(),
    ),
    vscode.commands.registerCommand(
      "leetknight._openAndReset",
      (slug: string) => openAndReset(slug, practice),
    ),
  );

  const practiceView = vscode.window.createTreeView("leetknight.practice", {
    treeDataProvider: practice,
  });
  context.subscriptions.push(practiceView);

  checkPython3();

  updateActiveContext();
  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor(() => updateActiveContext()),
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeWorkspaceFolders(() => {
      const newRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      practice.setWorkspaceRoot(newRoot);
    }),
  );

  if (root) {
    // Auto-open scaffolded Solution.java files.
    const solutionWatcher = vscode.workspace.createFileSystemWatcher(
      `**/*/${SOLUTION_FILENAME}`,
    );
    let openDebounce: ReturnType<typeof setTimeout> | undefined;
    const onCreate = (uri: vscode.Uri) => {
      if (openDebounce) clearTimeout(openDebounce);
      openDebounce = setTimeout(() => {
        vscode.commands.executeCommand("vscode.open", uri);
      }, 300);
    };
    solutionWatcher.onDidCreate(onCreate);
    context.subscriptions.push(solutionWatcher);

    // Watch for pending.json from a fresh Submit-Accepted.
    const pendingUri = vscode.Uri.file(
      path.join(root, ".leetknight", "pending.json"),
    );
    const pendingWatcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(root, ".leetknight/pending.json"),
    );
    const onPending = () => handlePending(root, practice);
    pendingWatcher.onDidCreate(onPending);
    pendingWatcher.onDidChange(onPending);
    context.subscriptions.push(pendingWatcher);
    // Catch pending.json written while the extension was inactive.
    if (fs.existsSync(pendingUri.fsPath)) {
      handlePending(root, practice);
    }
  }
}

export function deactivate() {}

function workspaceRoot(): string | undefined {
  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!root) {
    vscode.window.showErrorMessage("LeetKnight: open a folder first.");
  }
  return root;
}

function requireInit(): string | undefined {
  const root = workspaceRoot();
  if (!root) return undefined;
  if (!fs.existsSync(reviewsPath(root))) {
    vscode.window.showErrorMessage(
      "LeetKnight: run 'LeetKnight: Initialize Workspace' first.",
    );
    return undefined;
  }
  return root;
}

function updateActiveContext(): void {
  const editor = vscode.window.activeTextEditor;
  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  let isProblem = false;
  if (editor && root) {
    const filePath = editor.document.uri.fsPath;
    if (path.basename(filePath) === SOLUTION_FILENAME) {
      const meta = path.join(path.dirname(filePath), META_FILENAME);
      if (fs.existsSync(meta)) {
        isProblem = true;
      }
    }
  }
  vscode.commands.executeCommand(
    "setContext",
    "leetknight.activeIsProblem",
    isProblem,
  );
}

function activeProblemSlug(root: string): string | undefined {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return undefined;
  const filePath = editor.document.uri.fsPath;
  if (path.basename(filePath) !== SOLUTION_FILENAME) return undefined;
  const problemDir = path.dirname(filePath);
  if (!fs.existsSync(path.join(problemDir, META_FILENAME))) return undefined;
  const rel = path.relative(root, problemDir);
  if (!rel || rel.startsWith("..") || rel.includes(path.sep)) return undefined;
  return rel;
}

function shellQuote(s: string): string {
  return "'" + s.replace(/'/g, "'\\''") + "'";
}

function bundledScript(name: string): string {
  return `python3 ${shellQuote(path.join(extensionRoot, "scripts", name))}`;
}

function checkPython3(): void {
  const child = child_process.spawn("python3", ["--version"], {
    stdio: "ignore",
    shell: false,
  });
  child.on("error", () => warnNoPython());
  child.on("exit", (code) => {
    if (code !== 0) warnNoPython();
  });
}

function warnNoPython(): void {
  vscode.window.showErrorMessage(
    "LeetKnight: `python3` not found on PATH. Install Python 3.10+ and ensure `python3 --version` works from your shell — the bundled scripts (new.py / test_leetcode.py / submit_leetcode.py / reset_problem.py) cannot run without it.",
  );
}

async function leetcodeEnv(): Promise<Record<string, string>> {
  const env: Record<string, string> = {};
  const session = await extensionContext.secrets.get(LEETCODE_SESSION_KEY);
  const csrf = await extensionContext.secrets.get(LEETCODE_CSRF_KEY);
  if (session) env["LEETCODE_SESSION"] = session;
  if (csrf) env["LEETCODE_CSRF"] = csrf;
  return env;
}

async function initWorkspace() {
  const root = workspaceRoot();
  if (!root) return;

  const dir = path.join(root, ".leetknight");
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

  const p = reviewsPath(root);
  if (!fs.existsSync(p)) {
    saveReviews(root, { version: 1, problems: {} });
  }

  const readme = path.join(root, "README.md");
  if (!fs.existsSync(readme)) {
    fs.writeFileSync(
      readme,
      `# LeetKnight workspace

This folder is a LeetKnight workspace. Ratings and attempt history live in
\`.leetknight/reviews.json\`.

## Getting started

1. Open the **LeetKnight** activity-bar entry to see the Practice panel.
2. Run **LeetKnight: Set LeetCode Cookies** (from the Command Palette) to paste
   \`LEETCODE_SESSION\` and \`csrftoken\` from your browser DevTools.
3. Run **LeetKnight: Search LeetCode** or **LeetKnight: New Problem from URL** to
   scaffold a problem. Each problem lives in its own folder:
   \`<slug>/Solution.java\`, \`<slug>/notes.md\`, \`<slug>/.leetknight.json\`.
4. With a \`Solution.java\` open, use the ▶ / ☁️ / ↻ buttons in the editor
   toolbar to test / submit / reset.
5. After a Submit-Accepted, LeetKnight pops a modal asking you to rate
   Hard / Medium / Easy. The Practice panel groups your problems by that
   rating so the ones you found hardest bubble to the top.
`,
    );
  }

  vscode.window.showInformationMessage("LeetKnight workspace ready.");
}

async function newProblem() {
  const root = requireInit();
  if (!root) return;

  const url = await vscode.window.showInputBox({
    prompt: "LeetCode problem URL",
    placeHolder: "https://leetcode.com/problems/two-sum/",
    validateInput: (v) =>
      v.startsWith("http://") || v.startsWith("https://")
        ? undefined
        : "Please enter a full URL",
  });
  if (!url) return;

  await runInTerminal(`${bundledScript("new.py")} ${shellQuote(url)}`);
}

async function runTests() {
  const root = requireInit();
  if (!root) return;
  const slug = activeProblemSlug(root);
  if (!slug) {
    vscode.window.showErrorMessage(
      "LeetKnight: open a scaffolded Solution.java first.",
    );
    return;
  }
  const env = await leetcodeEnv();
  if (!env["LEETCODE_SESSION"] || !env["LEETCODE_CSRF"]) {
    await promptForCookies();
    return;
  }
  await runInTerminal(
    `${bundledScript("test_leetcode.py")} ${shellQuote(slug)}`,
    env,
  );
}

async function submit() {
  const root = requireInit();
  if (!root) return;
  const slug = activeProblemSlug(root);
  if (!slug) {
    vscode.window.showErrorMessage(
      "LeetKnight: open a scaffolded Solution.java first.",
    );
    return;
  }
  const env = await leetcodeEnv();
  if (!env["LEETCODE_SESSION"] || !env["LEETCODE_CSRF"]) {
    await promptForCookies();
    return;
  }
  await runInTerminal(
    `${bundledScript("submit_leetcode.py")} ${shellQuote(slug)}`,
    env,
  );
}

async function promptForCookies() {
  const choice = await vscode.window.showWarningMessage(
    "LeetCode cookies not set. Run 'LeetKnight: Set LeetCode Cookies' first.",
    "Set cookies now",
  );
  if (choice === "Set cookies now") {
    await setLeetcodeCookies();
  }
}

async function resetProblem() {
  const root = requireInit();
  if (!root) return;
  const slug = activeProblemSlug(root);
  if (!slug) {
    vscode.window.showErrorMessage(
      "LeetKnight: open a scaffolded Solution.java first.",
    );
    return;
  }
  await runReset(slug);
}

async function runReset(slug: string): Promise<void> {
  await runInTerminal(`${bundledScript("reset_problem.py")} ${shellQuote(slug)}`);
}

async function pickRandom(practice: PracticeProvider) {
  const root = requireInit();
  if (!root) return;
  const slug = randomTrackedSlug(root);
  if (!slug) {
    vscode.window.showInformationMessage(
      "LeetKnight: no practice problems yet. Solve and submit one to add it here.",
    );
    return;
  }
  await openAndReset(slug, practice);
  const entry = getEntry(root, slug);
  if (entry) {
    vscode.window.showInformationMessage(`Practicing: ${entry.title}`);
  }
}

async function openAndReset(slug: string, practice: PracticeProvider) {
  const root = requireInit();
  if (!root) return;
  const problemDir = path.join(root, slug);
  const solutionPath = path.join(problemDir, SOLUTION_FILENAME);
  const entry = getEntry(root, slug);

  if (!fs.existsSync(solutionPath)) {
    if (!entry) {
      vscode.window.showErrorMessage(
        `LeetKnight: no metadata for '${slug}'. Try 'LeetKnight: New Problem from URL'.`,
      );
      return;
    }
    // Folder is missing (user deleted it). Re-scaffold from the stored URL.
    await runInTerminal(`${bundledScript("new.py")} ${shellQuote(entry.url)}`);
    // Solution.java will auto-open via the FileSystemWatcher when new.py finishes.
    return;
  }

  await vscode.commands.executeCommand(
    "vscode.open",
    vscode.Uri.file(solutionPath),
  );
  await runReset(slug);
  practice.refresh();
}

async function setLeetcodeCookies() {
  const session = await vscode.window.showInputBox({
    prompt:
      "Paste LEETCODE_SESSION (DevTools > Application > Cookies > leetcode.com). Submit empty to clear.",
    password: true,
    ignoreFocusOut: true,
  });
  if (session === undefined) return;

  const csrf = await vscode.window.showInputBox({
    prompt: "Paste csrftoken (same DevTools panel). Submit empty to clear.",
    password: true,
    ignoreFocusOut: true,
  });
  if (csrf === undefined) return;

  const cleared: string[] = [];
  const stored: string[] = [];

  if (session.trim() === "") {
    await extensionContext.secrets.delete(LEETCODE_SESSION_KEY);
    cleared.push("LEETCODE_SESSION");
  } else {
    await extensionContext.secrets.store(LEETCODE_SESSION_KEY, session.trim());
    stored.push("LEETCODE_SESSION");
  }
  if (csrf.trim() === "") {
    await extensionContext.secrets.delete(LEETCODE_CSRF_KEY);
    cleared.push("csrftoken");
  } else {
    await extensionContext.secrets.store(LEETCODE_CSRF_KEY, csrf.trim());
    stored.push("csrftoken");
  }

  const parts: string[] = [];
  if (stored.length) parts.push(`stored ${stored.join(" + ")}`);
  if (cleared.length) parts.push(`cleared ${cleared.join(" + ")}`);
  vscode.window.showInformationMessage(`LeetKnight: ${parts.join("; ")}.`);
}

async function handlePending(root: string, practice: PracticeProvider) {
  const pendingPath = path.join(root, ".leetknight", "pending.json");
  if (!fs.existsSync(pendingPath)) return;

  let pending: PendingEntry;
  try {
    pending = JSON.parse(fs.readFileSync(pendingPath, "utf8")) as PendingEntry;
  } catch (e: any) {
    vscode.window.showErrorMessage(
      `LeetKnight: could not read pending.json: ${e.message || e}`,
    );
    fs.rmSync(pendingPath, { force: true });
    return;
  }

  try {
    upsertOnSubmit(root, pending);
    practice.refresh();
  } finally {
    fs.rmSync(pendingPath, { force: true });
  }

  const choice = await vscode.window.showInformationMessage(
    `Accepted: ${pending.title}. How hard was this?`,
    { modal: true },
    "Hard",
    "Medium",
    "Easy",
  );
  const rating: Rating =
    choice === "Hard" ? "hard" : choice === "Medium" ? "medium" : "easy";
  setRating(root, pending.slug, rating);
  practice.refresh();
}

interface LeetcodeSearchResult {
  title: string;
  titleSlug: string;
  difficulty: string;
  acRate: number;
  paidOnly: boolean;
}

let cachedAllProblems: LeetcodeSearchResult[] | undefined;

async function fetchAllLeetcodeProblems(): Promise<LeetcodeSearchResult[]> {
  if (cachedAllProblems) return cachedAllProblems;
  // /api/problems/all/ is the REST catalog endpoint — works anonymously and
  // returns ~4000 problems in one ~1 MB JSON blob. The GraphQL
  // problemsetQuestionList field was deprecated; its V2 successor walls
  // searchKeyword behind auth, so client-side filter over this REST list
  // is the simplest no-auth path.
  const r = await fetch("https://leetcode.com/api/problems/all/", {
    headers: { "User-Agent": "LeetKnight/1.0" },
  });
  if (!r.ok) {
    throw new Error(`LeetCode catalog failed: HTTP ${r.status}`);
  }
  const j: any = await r.json();
  const levels = ["", "Easy", "Medium", "Hard"];
  cachedAllProblems = ((j?.stat_status_pairs as any[]) || []).map((entry) => {
    const stat = entry?.stat || {};
    const total = stat.total_submitted || 0;
    return {
      title: stat.question__title || "",
      titleSlug: stat.question__title_slug || "",
      difficulty: levels[entry?.difficulty?.level || 0] || "?",
      acRate: total > 0 ? (stat.total_acs / total) * 100 : 0,
      paidOnly: !!entry?.paid_only,
    };
  });
  return cachedAllProblems;
}

async function fetchLeetcodeQuestions(
  searchKeywords: string,
): Promise<LeetcodeSearchResult[]> {
  const all = await fetchAllLeetcodeProblems();
  const needle = searchKeywords.toLowerCase().trim();
  if (!needle) return all.slice(0, 30);
  return all
    .filter((q) => q.title.toLowerCase().includes(needle))
    .slice(0, 30);
}

async function searchLeetcode() {
  const root = requireInit();
  if (!root) return;

  const query = await vscode.window.showInputBox({
    prompt: "Search LeetCode problems by title or keyword",
    placeHolder: "two sum",
  });
  if (!query) return;

  const questions = await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "Searching LeetCode...",
    },
    async () => {
      try {
        return await fetchLeetcodeQuestions(query);
      } catch (e: any) {
        vscode.window.showErrorMessage(`LeetKnight: ${e.message}`);
        return [];
      }
    },
  );

  if (questions.length === 0) {
    vscode.window.showInformationMessage(
      "LeetKnight: no LeetCode problems match that query.",
    );
    return;
  }

  const picks = questions.map((q) => ({
    label: `${q.title}${q.paidOnly ? " 🔒" : ""}`,
    description: `${q.difficulty} · ${q.acRate.toFixed(1)}% AC`,
    detail: `https://leetcode.com/problems/${q.titleSlug}/`,
    question: q,
  }));

  const picked = await vscode.window.showQuickPick(picks, {
    placeHolder: "Pick a problem to scaffold",
    matchOnDescription: true,
    matchOnDetail: true,
  });
  if (!picked) return;

  if (picked.question.paidOnly) {
    vscode.window.showErrorMessage(
      "LeetKnight: this is a premium-only LeetCode problem and cannot be scaffolded without a paid subscription.",
    );
    return;
  }

  await runInTerminal(`${bundledScript("new.py")} ${shellQuote(picked.detail)}`);
}
