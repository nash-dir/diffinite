/** Pure active-process bookkeeping, kept separate from VS Code APIs for tests. */
export interface TrackableProcess {
  once(event: "close", listener: (...args: unknown[]) => void): unknown;
  removeListener(event: "close", listener: (...args: unknown[]) => void): unknown;
}

export interface ClosableProcess extends TrackableProcess {
  readonly exitCode?: number | null;
  readonly signalCode?: string | null;
}

/** Wait for close without allowing a missing child-process event to hang forever. */
export function waitForProcessClose(
  process: ClosableProcess,
  timeoutMs: number,
): Promise<boolean> {
  if (process.exitCode != null || process.signalCode != null) {
    return Promise.resolve(true);
  }
  return new Promise((resolve) => {
    let settled = false;
    const finish = (closed: boolean): void => {
      if (settled) { return; }
      settled = true;
      clearTimeout(timer);
      process.removeListener("close", onClose);
      resolve(closed);
    };
    const onClose = (): void => finish(true);
    const timer = setTimeout(() => finish(false), timeoutMs);
    process.once("close", onClose);
  });
}

export class ActiveProcessRegistry<T extends TrackableProcess = TrackableProcess> {
  private readonly processes = new Set<T>();
  private readonly releases = new Map<T, () => void>();

  public get size(): number { return this.processes.size; }

  public track(process: T): () => void {
    const previousRelease = this.releases.get(process);
    if (previousRelease) { return previousRelease; }

    this.processes.add(process);
    const release = (): void => {
      process.removeListener("close", release);
      this.processes.delete(process);
      this.releases.delete(process);
    };
    this.releases.set(process, release);
    process.once("close", release);
    return release;
  }

  public release(process: T): void {
    this.releases.get(process)?.();
  }

  public async terminateAll(terminate: (process: T) => Promise<void>): Promise<void> {
    const outcomes = await Promise.allSettled(
      [...this.processes].map(async (process) => {
        try {
          await terminate(process);
        } finally {
          // A faulty child may never emit close; the registry must not retain it.
          this.release(process);
        }
      }),
    );
    const failures = outcomes
      .filter((outcome): outcome is PromiseRejectedResult => outcome.status === "rejected")
      .map((outcome) => outcome.reason);
    if (failures.length) {
      throw new AggregateError(failures, "One or more analyzer processes could not be terminated");
    }
  }
}
