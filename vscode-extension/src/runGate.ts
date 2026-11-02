/** A small non-queuing gate used to reject overlapping analysis runs. */
export class RunGate {
  private occupied = false;

  public tryEnter(): boolean {
    if (this.occupied) { return false; }
    this.occupied = true;
    return true;
  }

  public leave(): void {
    this.occupied = false;
  }
}
