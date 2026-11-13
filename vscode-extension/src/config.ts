/**
 * Configuration helpers — reads diffinite settings from VSCode.
 */
import * as vscode from "vscode";

export interface BatesPreset {
  name: string;
  prefix: string;
  suffix?: string;
  nextBatesNumber?: number;
}

export function getPythonPath(): string {
  const config = vscode.workspace.getConfiguration("diffinite");
  return config.get<string>("pythonPath", "python");
}

export function getDefaultMode(): string {
  const config = vscode.workspace.getConfiguration("diffinite");
  return config.get<string>("defaultMode", "deep");
}

export function getBatesPresets(): BatesPreset[] {
  const config = vscode.workspace.getConfiguration("diffinite");
  return config.get<BatesPreset[]>("batesPresets", []);
}

export function getPdfFont(): string {
  const config = vscode.workspace.getConfiguration("diffinite");
  return config.get<string>("pdfFont", "");
}

export function getPdfLang(): string {
  const config = vscode.workspace.getConfiguration("diffinite");
  return config.get<string>("pdfLang", "ko");
}
