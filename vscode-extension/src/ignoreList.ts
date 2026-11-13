/**
 * Global Exclusion List Manager (.diffignore)
 */
import * as vscode from "vscode";
import * as fs from "fs";
import { defaultIgnoreFilePath } from "./inputFreeze";

// Written only when the user opens the list and it does not exist yet. Every
// example is commented out: an active rule silently removes matching inputs
// from every later analysis, so none is enabled without the user choosing it.
// The examples are anchored ("/name/") so they match only at the folder root.
export const DEFAULT_IGNORE_PATTERNS = `# Diffinite Global Exclusion List (~/.diffignore)
#
# WARNING: every active (uncommented) line removes matching files and folders
# from EVERY analysis and export, in every case, until you delete it. Excluded
# files are not compared and are not listed as unmatched. Each report counts
# what the rules removed ("Inputs excluded by policy") and lists it unless the
# uncompared files list is set to Omit (a removed folder is listed once,
# without its contents). The report also records this file's SHA-256.
# Secrets (.env, private keys, credential files) need no rule here: the
# "Sensitive files" option in the Options panel excludes them by default.
#
# Syntax (subset of .gitignore):
#   name       matches a file or folder called "name" at ANY depth
#              (e.g. "build" also removes src/main/java/com/acme/build/)
#   name/      matches only folders called "name", at any depth
#   /name/     matches the folder "name" only at the top of A and B
#   *.ext      matches files with that extension at any depth
#   src/*.py   a pattern containing "/" is matched from the top; "*" does not
#              cross "/" (src/a/b.py is not matched)
#   a/**/b     "**" matches any number of folders
# Matching is case-sensitive on every operating system: "*.java" does not
# match Foo.JAVA, and "thumbs.db" does not match Thumbs.db. Add one line per
# spelling you want to exclude.
# Not supported: "!" negation (a line "!x" matches only a name that is
# literally "!x") and "\\" escapes. Spaces at the start and end of a line are
# removed. Lines starting with # are comments.
#
# Examples (remove the leading "# " to enable one):
# /node_modules/
# /.git/
# /.venv/
# /dist/
# /build/
# /target/
`;

/**
 * Returns the path to the global ~/.diffignore file.
 */
export function getIgnoreFilePath(): string {
  return defaultIgnoreFilePath();
}

/**
 * Ensures ~/.diffignore exists (creates boilerplate if not), then opens it in VS Code.
 */
export async function editIgnoreList(): Promise<void> {
  const ignorePath = getIgnoreFilePath();

  if (!fs.existsSync(ignorePath)) {
    try {
      fs.writeFileSync(ignorePath, DEFAULT_IGNORE_PATTERNS, "utf-8");
      vscode.window.showInformationMessage("Created ~/.diffignore with no active rules (examples are commented out). Rules you enable apply to every later analysis.");
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
