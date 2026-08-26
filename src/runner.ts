import * as vscode from "vscode";

let cachedTerminal: vscode.Terminal | undefined;
let cachedEnvKey: string | undefined;

export async function runInTerminal(
  cmd: string,
  env: Record<string, string> = {},
): Promise<void> {
  const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!root) return;

  const envKey = JSON.stringify(env);

  if (
    !cachedTerminal ||
    cachedTerminal.exitStatus !== undefined ||
    envKey !== cachedEnvKey
  ) {
    cachedTerminal?.dispose();
    cachedEnvKey = envKey;
    cachedTerminal = vscode.window.createTerminal({
      name: "leet.io",
      cwd: root,
      env,
    });
  }
  cachedTerminal.show();
  cachedTerminal.sendText(cmd);
}
