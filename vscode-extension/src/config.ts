/**
 * Configuration helpers — reads diffinite settings from VSCode.
 */
import * as vscode from "vscode";

export function getPythonPath(): string {
  const config = vscode.workspace.getConfiguration("diffinite");
  return config.get<string>("pythonPath", "python");
}

export function getDefaultMode(): string {
  const config = vscode.workspace.getConfiguration("diffinite");
  return config.get<string>("defaultMode", "deep");
}
