"""Entry point of the child process the studio starts: `python -m studio._child <stem args>`.

It runs the same command line as `python -m stem`. The only addition is that on
Windows a Ctrl+Break sent by the studio is turned into a KeyboardInterrupt, so
stopping a run from the UI saves progress exactly like Ctrl+C in a terminal
(on Linux and macOS the studio sends SIGINT, which Python already handles).
"""
from __future__ import annotations

import signal
import sys


def _interrupt(_signum, _frame):
    raise KeyboardInterrupt


def main() -> int:
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _interrupt)
    from stem.__main__ import main as stem_main
    return stem_main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
