/**
 * Diffinite VSCode Extension — entry point.
 *
 * Registers commands and initializes the extension.
 */
import * as vscode from "vscode";
import { compareDirectories } from "./compareCommand";

export function activate(context: vscode.ExtensionContext): void {
  const compareCmd = vscode.commands.registerCommand(
    "diffinite.compare",
    () => compareDirectories(context)
  );
  context.subscriptions.push(compareCmd);
}

export function deactivate(): void {
  // nothing to clean up
}
