/**
 * Diffinite VSCode Extension — entry point.
 *
 * Registers commands and initializes the extension.
 */
import * as vscode from "vscode";
import { compareDirectories } from "./compareCommand";
import { showHelp } from "./helpViewer";
import { editIgnoreList } from "./ignoreList";
import { terminateAllProcesses } from "./runner";
import { disposeFailureChannel } from "./failureNotice";

export function activate(context: vscode.ExtensionContext): void {
  const compareCmd = vscode.commands.registerCommand(
    "diffinite.compare",
    () => compareDirectories(context)
  );
  const helpCmd = vscode.commands.registerCommand(
    "diffinite.help",
    () => showHelp(context)
  );
  const ignoreCmd = vscode.commands.registerCommand(
    "diffinite.editIgnoreList",
    () => editIgnoreList()
  );
  context.subscriptions.push(compareCmd, helpCmd, ignoreCmd);
}

export async function deactivate(): Promise<void> {
  await terminateAllProcesses();
  disposeFailureChannel();
}
