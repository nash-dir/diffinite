/** Show a classified failure: a short notification plus full text in an output channel. */
import * as vscode from "vscode";
import { classifyFailure } from "./failureClassifier";

let channel: vscode.OutputChannel | undefined;

function outputChannel(): vscode.OutputChannel {
  if (!channel) { channel = vscode.window.createOutputChannel("Diffinite"); }
  return channel;
}

export async function showFailure(stage: string, error: unknown): Promise<void> {
  const failure = classifyFailure(error);
  if (failure.kind === "cancelled") {
    void vscode.window.showInformationMessage(`Diffinite ${stage}: cancelled. ${failure.action}`);
    return;
  }
  const out = outputChannel();
  out.appendLine(`[${new Date().toISOString()}] ${stage} — ${failure.title} (${failure.kind})`);
  out.appendLine(failure.details);
  out.appendLine("");
  const choice = await vscode.window.showErrorMessage(
    `Diffinite ${stage} failed — ${failure.title}. ${failure.action}`,
    "Show Details",
  );
  if (choice === "Show Details") { out.show(true); }
}

export function disposeFailureChannel(): void {
  channel?.dispose();
  channel = undefined;
}
