"""Allow ``python -m diffinite``."""

import multiprocessing

from diffinite.cli import main

# Required for PyInstaller frozen executables.
# Without this, ProcessPoolExecutor child processes crash on Windows.
# Ref: https://docs.python.org/3/library/multiprocessing.html#multiprocessing.freeze_support
multiprocessing.freeze_support()
main()
