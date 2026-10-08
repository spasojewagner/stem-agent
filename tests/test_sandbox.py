import os
import textwrap

from stem.sandbox import run_code


def tool(tmp_path, body):
    p = tmp_path / "t.py"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_returns_value_and_bridges_env_calls(tmp_path):
    p = tool(tmp_path, """
        def run(env, x=1):
            return {"double": env.double(n=x), "again": env.double(n=x + 1)}
    """)
    out, calls = run_code(p, {"x": 4}, lambda a, args: args["n"] * 2)
    assert '"double": 8' in out and '"again": 10' in out and calls == 2


def test_errors_come_back_as_text(tmp_path):
    p = tool(tmp_path, "def run(env):\n    raise ValueError('nope')\n")
    out, _ = run_code(p, {}, None)
    assert out.startswith("TOOL ERROR") and "nope" in out


def test_timeout(tmp_path):
    p = tool(tmp_path, "def run(env):\n    while True:\n        pass\n")
    out, _ = run_code(p, {}, None, timeout=2)
    assert "timed out" in out


def test_env_call_limit(tmp_path):
    p = tool(tmp_path, """
        def run(env):
            for _ in range(100):
                env.ping()
    """)
    out, calls = run_code(p, {}, lambda a, args: 1, max_env_calls=10)
    assert "limit" in out and calls == 11


def test_api_key_not_visible(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_secret_value")
    p = tool(tmp_path, "import os\ndef run(env):\n    return str(os.environ.get('GROQ_API_KEY'))\n")
    out, _ = run_code(p, {}, None)
    assert out == "None"


def test_barriers(tmp_path):
    here = os.path.abspath(__file__)
    cases = {
        "file outside scratch": f"def run(env):\n    return open({here!r}).read()[:10]\n",
        "listing directories": "import os\ndef run(env):\n    return os.listdir('/')\n",
        "subprocess": "def run(env):\n    import subprocess\n    return 'x'\n",
        "os.system": "import os\ndef run(env):\n    return os.system('echo hi')\n",
        "network": "import socket\ndef run(env):\n    socket.socket()\n    return 'x'\n",
        "importing non-stdlib source": f"import importlib.util\ndef run(env):\n"
                                       f"    s = importlib.util.spec_from_file_location('m', {here!r})\n"
                                       f"    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)\n    return 'x'\n",
    }
    for name, code in cases.items():
        out, _ = run_code(tool(tmp_path, code), {}, None)
        assert out.startswith("TOOL ERROR"), f"{name} was not blocked: {out[:120]}"


def test_scratch_files_and_stdlib_work(tmp_path):
    p = tool(tmp_path, """
        import json, re, statistics
        def run(env):
            with open("notes.txt", "w") as fh:
                fh.write("ok")
            return open("notes.txt").read() + str(statistics.fmean([1, 3]))
    """)
    out, _ = run_code(p, {}, None)
    assert out == "ok2.0"


def test_many_runs_leave_no_errors(tmp_path):
    """Windows can keep the scratch folder locked briefly; that must never surface as an error."""
    p = tool(tmp_path, "def run(env):\n    raise ValueError('x')\n")
    for _ in range(15):
        out, _ = run_code(p, {}, None)
        assert out.startswith("TOOL ERROR")
