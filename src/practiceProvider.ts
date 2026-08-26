import * as vscode from "vscode";
import { allTrackedSorted, ProblemEntry, Rating } from "./reviews";

type GroupKey = "hard" | "medium" | "easy";

const GROUP_META: Record<
  GroupKey,
  { icon: string; label: string }
> = {
  hard: { icon: "🔴", label: "Hard" },
  medium: { icon: "🟡", label: "Medium" },
  easy: { icon: "🟢", label: "Easy" },
};

const GROUP_ORDER: GroupKey[] = ["hard", "medium", "easy"];

export class PracticeProvider
  implements vscode.TreeDataProvider<PracticeNode>
{
  private _onDidChange = new vscode.EventEmitter<
    PracticeNode | undefined | void
  >();
  readonly onDidChangeTreeData = this._onDidChange.event;

  constructor(private workspaceRoot: string | undefined) {}

  refresh(): void {
    this._onDidChange.fire();
  }

  setWorkspaceRoot(root: string | undefined): void {
    this.workspaceRoot = root;
    this.refresh();
  }

  getTreeItem(element: PracticeNode): vscode.TreeItem {
    return element;
  }

  getChildren(element?: PracticeNode): PracticeNode[] {
    if (!this.workspaceRoot) {
      return [emptyStateNode("Open a folder and run 'leet.io: Initialize Workspace' to begin.")];
    }

    if (!element) {
      const groups = allTrackedSorted(this.workspaceRoot);
      const nodes: PracticeNode[] = [];
      let total = 0;
      for (const key of GROUP_ORDER) {
        const entries = groups[key];
        if (entries.length === 0) continue;
        total += entries.length;
        nodes.push(new GroupNode(key, entries));
      }
      if (total === 0) {
        return [
          emptyStateNode(
            "No practice problems yet. Solve one and submit to add it here.",
          ),
        ];
      }
      return nodes;
    }

    if (element instanceof GroupNode) {
      return element.entries.map((e) => new ProblemNode(e));
    }

    return [];
  }
}

class PracticeNode extends vscode.TreeItem {}

class GroupNode extends PracticeNode {
  constructor(
    public readonly rating: GroupKey,
    public readonly entries: ProblemEntry[],
  ) {
    const meta = GROUP_META[rating];
    super(
      `${meta.icon} ${meta.label} (${entries.length})`,
      vscode.TreeItemCollapsibleState.Expanded,
    );
    this.contextValue = "leetio.group";
  }
}

class ProblemNode extends PracticeNode {
  constructor(public readonly entry: ProblemEntry) {
    super(entry.title, vscode.TreeItemCollapsibleState.None);
    const lastDate = entry.lastAttempt.slice(0, 10);
    this.description = `${entry.difficulty} · last ${lastDate}`;
    this.tooltip = `${entry.title}\n${entry.url}\nAttempts: ${entry.attempts}`;
    this.iconPath = new vscode.ThemeIcon("file-code");
    this.contextValue = "leetio.problem";
    this.command = {
      command: "leetio._openAndReset",
      title: "Practice this problem",
      arguments: [entry.slug],
    };
  }
}

function emptyStateNode(message: string): PracticeNode {
  const node = new PracticeNode(message, vscode.TreeItemCollapsibleState.None);
  node.iconPath = new vscode.ThemeIcon("info");
  return node;
}

export { PracticeNode };
export type { Rating };
