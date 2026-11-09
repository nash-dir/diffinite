/**
 * Shared helpers for safely building webview HTML.
 *
 * Hoisted here so the escaping rules and nonce generation can't drift between
 * the options panel, result viewer, and tree viewer webviews.
 */
import { randomBytes } from "crypto";

/** Escape a value for safe interpolation into HTML text or a double- or single-quoted attribute. */
export function escHtml(s: unknown): string {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Theme tokens shared by every webview.
 *
 * Each token maps to a VS Code theme color (exposed to webviews as
 * `--vscode-*` CSS variables), so Light, Dark and High Contrast themes all
 * work. The literal after each comma is only a fallback for rendering the
 * HTML outside VS Code (e.g. a browser preview); inside VS Code the theme
 * value always wins.
 */
export const THEME_CSS = `
  :root {
    --bg: var(--vscode-editor-background, #ffffff);
    --bg-surface: var(--vscode-sideBar-background, var(--vscode-editorWidget-background, #f3f3f3));
    --bg-block: var(--vscode-editorWidget-background, #f3f3f3);
    --fg: var(--vscode-foreground, #3b3b3b);
    --fg-dim: var(--vscode-descriptionForeground, #6f6f6f);
    --accent: var(--vscode-textLink-foreground, #005fb8);
    --border: var(--vscode-contrastBorder, var(--vscode-panel-border, var(--vscode-widget-border, #c8c8c8)));
    --focus: var(--vscode-focusBorder, #005fb8);
    --error: var(--vscode-errorForeground, #c72e0f);
    --warning: var(--vscode-editorWarning-foreground, #bf8803);
    --info: var(--vscode-editorInfo-foreground, #1a85ff);
    --added-fg: var(--vscode-gitDecoration-addedResourceForeground, #388a34);
    --deleted-fg: var(--vscode-gitDecoration-deletedResourceForeground, #ad0707);
    --btn-bg: var(--vscode-button-background, #005fb8);
    --btn-fg: var(--vscode-button-foreground, #ffffff);
    --btn-hover: var(--vscode-button-hoverBackground, #0258a8);
    --btn-border: var(--vscode-button-border, var(--vscode-contrastBorder, transparent));
    --btn2-bg: var(--vscode-button-secondaryBackground, #e5e5e5);
    --btn2-fg: var(--vscode-button-secondaryForeground, #3b3b3b);
    --btn2-hover: var(--vscode-button-secondaryHoverBackground, #cccccc);
    --input-bg: var(--vscode-input-background, #ffffff);
    --input-fg: var(--vscode-input-foreground, #3b3b3b);
    --input-border: var(--vscode-input-border, var(--border));
    --hover-bg: var(--vscode-list-hoverBackground, rgba(128,128,128,.12));
    --badge-bg: var(--vscode-badge-background, #cccccc);
    --badge-fg: var(--vscode-badge-foreground, #3b3b3b);
    --code-font: var(--vscode-editor-font-family, Consolas, "Courier New", monospace);
    --diff-add-line: var(--vscode-diffEditor-insertedLineBackground, rgba(155,185,85,.2));
    --diff-del-line: var(--vscode-diffEditor-removedLineBackground, rgba(255,0,0,.2));
    --diff-add-text: var(--vscode-diffEditor-insertedTextBackground, rgba(155,185,85,.4));
    --diff-del-text: var(--vscode-diffEditor-removedTextBackground, rgba(255,0,0,.4));
    --diff-add-border: var(--vscode-diffEditor-insertedTextBorder, transparent);
    --diff-del-border: var(--vscode-diffEditor-removedTextBorder, transparent);
    --diff-move-border: var(--vscode-diffEditor-move-border, #8b8b8b);
  }
  body {
    font-family: var(--vscode-font-family, "Segoe UI", "Noto Sans KR", sans-serif);
    color: var(--fg);
    background: var(--bg);
  }
  :focus-visible { outline: 1px solid var(--focus); outline-offset: 1px; }
  button { font-family: inherit; }
  .btn-primary { border: 1px solid var(--btn-border) !important; }
  button:disabled { opacity: .5; cursor: default; }
  input, select, textarea {
    font-family: inherit;
    background: var(--input-bg);
    color: var(--input-fg);
    border: 1px solid var(--input-border);
  }
  code, .mono { font-family: var(--code-font); }
`;

/**
 * Cryptographically-random alphanumeric nonce (32 chars) for the webview
 * Content-Security-Policy. Uses the CSPRNG (`crypto.randomBytes`) rather than
 * `Math.random()`.
 */
export function getNonce(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  const bytes = randomBytes(32);
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += chars.charAt(bytes[i] % chars.length);
  return s;
}
