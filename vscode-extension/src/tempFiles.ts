/** Collision-safe temporary JSON files with directory-scoped cleanup. */
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

export interface TempJsonFile {
  directory: string;
  filePath: string;
  cleanup: () => void;
}

export function createTempJsonFile(prefix: string): TempJsonFile {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  return {
    directory,
    filePath: path.join(directory, "payload.json"),
    cleanup: () => {
      try { fs.rmSync(directory, { recursive: true, force: true }); } catch { /* ignore */ }
    },
  };
}
