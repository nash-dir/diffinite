/**
 * Diffinite VSCode Extension — entry point.
 *
 * Registers commands and initializes the extension.
 */
import * as vscode from "vscode";
import { compareDirectories } from "./compareCommand";
import { showHelp } from "./helpViewer";
import { editIgnoreList } from "./ignoreList";

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

export function deactivate(): void {
  // nothing to clean up
}
