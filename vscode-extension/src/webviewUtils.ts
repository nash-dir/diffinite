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
    /* VS Code has no theme color for a word-level changed line or for changed
       whitespace. A warm neutral over the editor background (#f5f0e0 on white,
       near the reports' #f3eedb) and a grey (#dfdfdf on white, near the
       reports' #dedede) keep both apart from the added and removed tints. */
    --diff-chg-line: rgba(190,160,60,.16);
    --diff-ws-text: rgba(128,128,128,.25);
    /* High Contrast themes define contrastActiveBorder; elsewhere it is unset. */
    --focus-ring: var(--vscode-contrastActiveBorder, var(--focus));

    /* Spacing scale (4px base, as in the VS Code workbench). */
    --sp-1: 4px;
    --sp-2: 8px;
    --sp-3: 12px;
    --sp-4: 16px;
    --sp-5: 24px;
    --sp-6: 32px;

    /* Type scale, anchored on the editor UI font size the user configured. */
    --fs-base: var(--vscode-font-size, 13px);
    --fs-sm: 12px;
    --fs-xs: 11px;
    --fs-h2: 13px;
    --fs-h1: 16px;
    --control-h: 26px;
  }
  body {
    font-family: var(--vscode-font-family, "Segoe UI", "Noto Sans KR", sans-serif);
    font-size: var(--fs-base);
    line-height: 1.45;
    color: var(--fg);
    background: var(--bg);
    /* Never slant or embolden a font that has no italic or bold face (CJK file names). */
    font-synthesis: none;
  }
  /* Keyboard focus is always visible; mouse focus does not draw a ring. */
  :focus { outline: none; }
  :focus-visible { outline: 1px solid var(--focus-ring); outline-offset: 1px; }
  input:focus-visible, select:focus-visible, textarea:focus-visible { outline-offset: -1px; }

  /* Buttons: one primary action per view, everything else secondary. */
  button { font-family: inherit; font-size: var(--fs-base); line-height: 18px; }
  .btn-primary, .btn-secondary {
    min-height: var(--control-h); padding: 3px 12px; border-radius: 2px; cursor: pointer;
    white-space: nowrap;
  }
  .btn-primary { background: var(--btn-bg); color: var(--btn-fg); border: 1px solid var(--btn-border) !important; }
  .btn-primary:hover:not(:disabled) { background: var(--btn-hover); }
  .btn-secondary { background: var(--btn2-bg); color: var(--btn2-fg); border: 1px solid var(--btn-border); }
  .btn-secondary:hover:not(:disabled) { background: var(--btn2-hover); }
  .btn-link {
    background: none; border: 1px solid transparent; color: var(--accent); padding: 0 2px;
    cursor: pointer; text-decoration: none;
  }
  .btn-link:hover { text-decoration: underline; }
  button:disabled { opacity: .5; cursor: default; }

  input, select, textarea {
    font-family: inherit;
    font-size: var(--fs-base);
    background: var(--input-bg);
    color: var(--input-fg);
    border: 1px solid var(--input-border);
    border-radius: 2px;
  }
  input[type="checkbox"], input[type="radio"] { accent-color: var(--btn-bg); margin: 0; }
  /* High Contrast buttons are transparent, so draw checked controls in the text color. */
  body[class*="vscode-high-contrast"] input[type="checkbox"],
  body[class*="vscode-high-contrast"] input[type="radio"] { accent-color: var(--fg); }
  code, .mono { font-family: var(--code-font); }

  /* Figures line up in columns and do not shift when they change. */
  .num { font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }
  .dim { color: var(--fg-dim); }

  /* Notices are neutral. Only a condition that limits what the result covers
     (kind "warning", e.g. an incomplete analysis) gets a heavier rule, in the
     text color rather than a signal color, so nothing reads as a verdict. */
  .notice {
    margin: var(--sp-2) 0; padding: var(--sp-2) var(--sp-3);
    border: 1px solid var(--border); border-radius: 0;
  }
  .notice.warning { border-left: 3px solid var(--fg); }
  .notice-title { display: block; font-weight: 600; margin-bottom: 2px; }
  .notice-body { overflow-wrap: anywhere; }

  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
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
