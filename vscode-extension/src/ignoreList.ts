/**
 * Global Exclusion List Manager (.diffignore)
 */
import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import * as os from "os";

const DEFAULT_IGNORE_PATTERNS = `# Diffinite Global Exclusion List
# Patterns here will completely exclude matching files and directories
# from the forensic analysis, speeding up performance by up to 50x and
# preventing noise in the final PDF report.
#
# Syntax is similar to .gitignore (glob patterns matching filenames/dirnamess)

# Node / JS
node_modules
dist
build
.next
.nuxt

# Python
__pycache__
*.py[cod]
*$py.class
.venv
venv
env

# Java / JVM
*.class
target
.gradle

# OS / IDE
.DS_Store
Thumbs.db
.vscode
.idea
.git
`;

/**
 * Returns the path to the global ~/.diffignore file.
 */
export function getIgnoreFilePath(): string {
  return path.join(os.homedir(), ".diffignore");
}

/**
 * Ensures ~/.diffignore exists (creates boilerplate if not), then opens it in VS Code.
 */
export async function editIgnoreList(): Promise<void> {
  const ignorePath = getIgnoreFilePath();

  if (!fs.existsSync(ignorePath)) {
    try {
      fs.writeFileSync(ignorePath, DEFAULT_IGNORE_PATTERNS, "utf-8");
      vscode.window.showInformationMessage("Created default global exclusion list: ~/.diffignore");
    } catch (err) {
      vscode.window.showErrorMessage(`Failed to create ~/.diffignore: ${err}`);
      return;
    }
  }

  try {
    const document = await vscode.workspace.openTextDocument(ignorePath);
    await vscode.window.showTextDocument(document);
  } catch (err) {
    vscode.window.showErrorMessage(`Failed to open ~/.diffignore: ${err}`);
  }
}
