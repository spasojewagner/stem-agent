"""Child process that runs one genome-authored tool.

Protocol (one JSON object per line):
  parent -> child  {"args": {...}}
  child  -> parent {"type": "env", "action": str, "args": {...}}   environment call
  parent -> child  {"ok": true, "value": ...} | {"ok": false, "error": str}
  child  -> parent {"type": "result", "value": str} | {"type": "error", "error": str}

The tool module must define `run(env, **kwargs)`. `env.<action>(**args)`
forwards to the environment the parent is attached to.

Before the tool's code runs, a few soft barriers go up: no sockets, no
subprocesses, no listing directories, and files can only be opened inside
the tool's scratch directory. They stop accidents and casual shortcuts
(like reading the environment's source from disk). The container is the
real boundary.
"""
import builtins
import io
import json
import os
import socket
import sys
import sysconfig
import traceback
import types

_OUT = sys.stdout


def _send(obj):
    _OUT.write(json.dumps(obj, default=str) + "\n")
    _OUT.flush()


class _Env:
    def __getattr__(self, action):
        if action.startswith("_"):
            raise AttributeError(action)

        def call(*args, **kwargs):
            if args:
                kwargs = dict(kwargs, __pos__=list(args))
            _send({"type": "env", "action": action, "args": kwargs})
            line = sys.stdin.readline()
            if not line:
                raise RuntimeError("parent closed the channel")
            msg = json.loads(line)
            if not msg.get("ok"):
                raise RuntimeError(msg.get("error", "environment call failed"))
            return msg.get("value")
        return call


def _blocked(*_a, **_k):
    raise PermissionError("not available inside genome tools")


def _install_barriers():
    norm = lambda p: os.path.normcase(os.path.realpath(p))  # Windows paths are case-insensitive
    scratch = norm(os.getcwd())
    libs = {norm(p) for k in ("stdlib", "platstdlib", "purelib", "platlib")
            if (p := sysconfig.get_paths().get(k))}
    real_open, real_open_code = io.open, io.open_code

    def inside(path, roots):
        p = norm(os.fspath(path))
        return any(p == r or p.startswith(r + os.sep) for r in roots)

    def guarded_open(file, *a, **k):
        if isinstance(file, int) or not inside(file, {scratch}):
            raise PermissionError("genome tools may only open files in their scratch directory")
        return real_open(file, *a, **k)

    def guarded_open_code(path):
        if not inside(path, libs | {scratch}):
            raise PermissionError("genome tools may only import the standard library")
        return real_open_code(path)

    builtins.open = io.open = guarded_open
    io.open_code = guarded_open_code

    class _NoNetwork(socket.socket):
        def __init__(self, *a, **k):
            raise PermissionError("network access is disabled inside genome tools")
    socket.socket = _NoNetwork

    for name in ("system", "popen", "fork", "forkpty", "startfile", "listdir", "scandir", "walk",
                 "execv", "execve", "execl", "execle", "execlp", "execvp", "execvpe",
                 "spawnl", "spawnle", "spawnv", "spawnve", "posix_spawn", "posix_spawnp"):
        if hasattr(os, name):
            setattr(os, name, _blocked)
    sys.modules["subprocess"] = None  # `import subprocess` now raises ImportError


def main():
    path = sys.argv[1]
    request = json.loads(sys.stdin.readline() or "{}")
    sys.stdout = sys.stderr          # stray prints must not corrupt the protocol
    try:
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        _install_barriers()
        module = types.ModuleType("genome_tool")
        module.__file__ = "genome_tool.py"
        exec(compile(source, "genome_tool.py", "exec"), module.__dict__)
        fn = module.__dict__.get("run")
        if fn is None:
            raise AttributeError("tool module must define run(env, **kwargs)")
        value = fn(_Env(), **(request.get("args") or {}))
        if not isinstance(value, str):
            value = json.dumps(value, default=str)
        _send({"type": "result", "value": value})
    except BaseException as e:  # noqa: BLE001 - report everything to the parent
        _send({"type": "error", "error": f"{type(e).__name__}: {e}",
               "trace": traceback.format_exc()[-1200:]})


if __name__ == "__main__":
    main()
