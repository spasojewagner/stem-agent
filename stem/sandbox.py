"""Run genome-authored code in a separate Python process.

What this protects against: crashes, infinite loops, stray prints, reading
the API key from the environment, casual network use, unbounded calls into
the environment. What it does not: a determined attacker on the same user
account. Run the whole system in the provided container for that.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

RUNNER = Path(__file__).with_name("_tool_runner.py")
Bridge = Callable[[str, dict], Any]


def _child_env() -> dict[str, str]:
    keep = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG"}
    env = {k: v for k, v in os.environ.items() if k in keep}
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"})
    return env


def _limits() -> None:  # POSIX only: cap CPU time and memory of the child
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
    except Exception:
        pass


def run_code(path: Path, args: dict, bridge: Bridge | None, timeout: float = 30,
             max_env_calls: int = 5000, with_log: bool = False) -> tuple[str, int]:
    """Run `run(env, **args)` from the file at `path`.

    Returns (output_text, env_calls_made). Errors come back as text starting
    with 'TOOL ERROR', never as exceptions, so the agent can read them.
    """
    # ignore_cleanup_errors: on Windows the folder can stay locked for a moment
    # after the child exits (or while an antivirus scans it). Leftovers are harmless.
    with tempfile.TemporaryDirectory(prefix="stem_tool_", ignore_cleanup_errors=True) as cwd:
        proc = subprocess.Popen(
            [sys.executable, "-I", str(RUNNER), str(Path(path).resolve())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", cwd=cwd, env=_child_env(),
            preexec_fn=_limits if os.name == "posix" else None,
        )
        lines: "queue.Queue[str | None]" = queue.Queue()

        def pump() -> None:
            for line in proc.stdout:  # type: ignore[union-attr]
                lines.put(line)
            lines.put(None)

        threading.Thread(target=pump, daemon=True).start()
        stderr_chunks: list[str] = []
        err_thread = threading.Thread(target=lambda: stderr_chunks.append(proc.stderr.read()),  # type: ignore[union-attr]
                                      daemon=True)
        err_thread.start()

        def printed(text: str) -> str:
            """Append what the tool printed, when asked (print() goes to stderr in the child)."""
            if not with_log:
                return text
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            err_thread.join(timeout=1)
            out = "".join(stderr_chunks).strip()
            return f"{text}\n[printed by the tool]\n{out[-1500:]}" if out else text

        calls = 0
        deadline = time.monotonic() + timeout
        try:
            proc.stdin.write(json.dumps({"args": args}) + "\n")  # type: ignore[union-attr]
            proc.stdin.flush()  # type: ignore[union-attr]
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    return f"TOOL ERROR: timed out after {timeout}s ({calls} environment calls made)", calls
                try:
                    line = lines.get(timeout=left)
                except queue.Empty:
                    continue
                if line is None:
                    proc.wait(timeout=2)
                    err = "".join(stderr_chunks)[-800:]
                    return f"TOOL ERROR: process exited without a result. {err}".strip(), calls
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = msg.get("type")
                if kind == "env":
                    calls += 1
                    if bridge is None:
                        reply = {"ok": False, "error": "no environment attached"}
                    elif calls > max_env_calls:
                        reply = {"ok": False, "error": f"environment call limit ({max_env_calls}) reached"}
                    else:
                        try:
                            reply = {"ok": True, "value": bridge(msg.get("action", ""), msg.get("args") or {})}
                        except Exception as e:
                            reply = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                    proc.stdin.write(json.dumps(reply, default=str) + "\n")  # type: ignore[union-attr]
                    proc.stdin.flush()  # type: ignore[union-attr]
                elif kind == "result":
                    return printed(str(msg.get("value", ""))), calls
                elif kind == "error":
                    return printed(f"TOOL ERROR: {msg.get('error')}\n{msg.get('trace', '')}".strip()), calls
        except (BrokenPipeError, OSError) as e:
            return f"TOOL ERROR: {e}", calls
        finally:
            if proc.poll() is None:
                proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    stream.close()  # type: ignore[union-attr]
                except Exception:
                    pass
