/** Split a decoded text stream into whole lines across chunk boundaries. */
export class LineBuffer {
  private carry = "";

  /**
   * @param onLine receives each complete line, without its line ending.
   * @param maxCarryChars bound on an unterminated line kept between chunks,
   *   so a child that never prints a newline cannot grow memory without limit.
   */
  public constructor(
    private readonly onLine: (line: string) => void,
    private readonly maxCarryChars: number,
  ) {}

  public push(chunk: string): void {
    const parts = (this.carry + chunk).split(/\r?\n/);
    this.carry = (parts.pop() ?? "").slice(-this.maxCarryChars);
    for (const line of parts) { this.onLine(line); }
  }

  public flush(): void {
    if (!this.carry) { return; }
    const line = this.carry;
    this.carry = "";
    this.onLine(line);
  }
}

/**
 * "Step" message of a Python INFO log line (cli.py logging format), else null.
 * A trailing ellipsis (U+2026 or three periods) is dropped: progress text in
 * the extension carries no decorative punctuation.
 */
export function pipelineStepMessage(line: string): string | null {
  const match = /\[INFO\]\s+(Step\b.*)$/.exec(line);
  return match ? match[1].trim().replace(/\s*(?:\u{2026}|\.{3})$/u, "") : null;
}
