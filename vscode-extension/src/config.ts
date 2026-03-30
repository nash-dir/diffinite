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

export async function updateBatesPresetStart(
  presetName: string,
  nextNumber: number
): Promise<void> {
  const config = vscode.workspace.getConfiguration("diffinite");
  const presets = config.get<BatesPreset[]>("batesPresets", []);
  const idx = presets.findIndex((p) => p.name === presetName);
  if (idx >= 0) {
    presets[idx].nextBatesNumber = nextNumber;
    await config.update("batesPresets", presets, vscode.ConfigurationTarget.Global);
  }
}

export function getPdfFont(): string {
  const config = vscode.workspace.getConfiguration("diffinite");
  return config.get<string>("pdfFont", "");
}

export function getPdfLang(): string {
  const config = vscode.workspace.getConfiguration("diffinite");
  return config.get<string>("pdfLang", "ko");
}
