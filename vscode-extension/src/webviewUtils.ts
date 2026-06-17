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
