"""Commands started from the UI, run as child processes.

Only one job runs at a time: runs share the provider's rate limits and the
same runs/ folder, and the command line was written for one run at a time.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

MAX_LINES = 5000
KEEP_FINISHED = 20
STOP_GRACE_SECONDS = 45   # a provider rate-limit wait can take most of a minute


class Busy(RuntimeError):
    pass


@dataclass
class Job:
    id: str
    kind: str
    args: list[str]
    run: str | None = None
    status: str = "running"            # running | succeeded | failed | stopped
    exit_code: int | None = None
    started: float = field(default_factory=time.time)
    finished: float | None = None
    lines: list[str] = field(default_factory=list)
    dropped: int = 0                   # lines dropped from the start when the log grew too long
    stop_requested: bool = False

    def view(self, with_lines: bool = False) -> dict:
        out = {"id": self.id, "kind": self.kind, "command": "python -m stem " + " ".join(self.args),
               "run": self.run, "status": self.status, "exit_code": self.exit_code,
               "started": self.started, "finished": self.finished,
               "line_count": self.dropped + len(self.lines)}
        if with_lines:
            out["lines"] = list(self.lines)
            out["first_line"] = self.dropped
        return out


def default_command(args: list[str]) -> list[str]:
    return [sys.executable, "-u", "-m", "studio._child", *args]


class JobManager:
    def __init__(self, cwd: Path, command: Callable[[list[str]], list[str]] = default_command):
        self.cwd = cwd
        self.command = command
        self.jobs: dict[str, Job] = {}
        self._procs: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self.changed = threading.Condition(self._lock)

    # -- queries --------------------------------------------------------------
    def current(self) -> Job | None:
        with self._lock:
            return next((j for j in self.jobs.values() if j.status == "running"), None)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self.jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return sorted(self.jobs.values(), key=lambda j: j.started, reverse=True)

    def active_runs(self) -> set[str]:
        with self._lock:
            return {j.run for j in self.jobs.values() if j.status == "running" and j.run}

    def lines_since(self, job: Job, index: int) -> tuple[list[str], int]:
        """Lines from absolute index `index` on, and the index to ask for next time."""
        with self._lock:
            start = max(index - job.dropped, 0)
            new = job.lines[start:]
            return new, job.dropped + len(job.lines)

    # -- lifecycle ------------------------------------------------------------
    def start(self, kind: str, args: list[str], run: str | None = None) -> Job:
        with self._lock:
            running = next((j for j in self.jobs.values() if j.status == "running"), None)
            if running:
                raise Busy(f"another job is running: {running.kind} ({running.id})")
            job = Job(id=uuid.uuid4().hex[:12], kind=kind, args=list(args), run=run)
            env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
            kwargs: dict = {}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            proc = subprocess.Popen(self.command(job.args), cwd=self.cwd, env=env,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                    errors="replace", bufsize=1, **kwargs)
            self.jobs[job.id] = job
            self._procs[job.id] = proc
            self._trim()
        threading.Thread(target=self._pump, args=(job, proc), daemon=True).start()
        return job

    def stop(self, job_id: str) -> Job | None:
        """Interrupt like Ctrl+C: the command saves its progress and exits."""
        with self._lock:
            job, proc = self.jobs.get(job_id), self._procs.get(job_id)
            if not job or not proc or job.status != "running":
                return job
            job.stop_requested = True
        try:
            if os.name == "nt":
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.send_signal(signal.SIGINT)
        except OSError:
            pass

        def force_after_grace() -> None:
            try:
                proc.wait(timeout=STOP_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                proc.kill()
        threading.Thread(target=force_after_grace, daemon=True).start()
        return job

    def shutdown(self) -> None:
        for job in self.list():
            if job.status == "running":
                self.stop(job.id)

    def wait(self, job_id: str, timeout: float = 60) -> Job | None:
        deadline = time.time() + timeout
        with self.changed:
            while True:
                job = self.jobs.get(job_id)
                if not job or job.status != "running" or time.time() > deadline:
                    return job
                self.changed.wait(timeout=0.2)

    # -- internals ------------------------------------------------------------
    def _pump(self, job: Job, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        for raw in proc.stdout:
            with self.changed:
                job.lines.append(raw.rstrip("\n"))
                if len(job.lines) > MAX_LINES:
                    cut = len(job.lines) - MAX_LINES
                    del job.lines[:cut]
                    job.dropped += cut
                self.changed.notify_all()
        code = proc.wait()
        with self.changed:
            job.exit_code = code
            job.finished = time.time()
            if job.stop_requested:
                job.status = "stopped"
            else:
                job.status = "succeeded" if code == 0 else "failed"
            self._procs.pop(job.id, None)
            self.changed.notify_all()

    def _trim(self) -> None:
        finished = sorted((j for j in self.jobs.values() if j.status != "running"), key=lambda j: j.started)
        for j in finished[:-KEEP_FINISHED] if len(finished) > KEEP_FINISHED else []:
            self.jobs.pop(j.id, None)
