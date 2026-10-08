"""The genome: everything that is allowed to change, stored as a folder.

    genome.json        identity, system prompt, behaviour mode
    tools/<name>.py    code the agent wrote for itself: def run(env, **kwargs)
    tools/<name>.json  name, description, JSON-schema parameters
    skills/<name>.md   written procedures the agent can read while working
    subagents/<n>.json specialists it can delegate to
    hooks/<event>.py   on_task_start(env, task) -> extra context
                       on_finish(env, answer)   -> "" to accept, or a reason to keep working

A fresh stem genome has none of these filled in. Each accepted change is a
git commit inside the genome folder, so differentiation can be read with
`git log -p`.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

NAME = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
HOOK_EVENTS = ("on_task_start", "on_finish")
MODEL_TIERS = ("act", "fast")

DEFAULT_MODE = {"max_steps": 12, "temperature": 0.2, "plan_first": False,
                "reflect_every": 0, "model_tier": "act"}


class GenomeError(ValueError):
    pass


def rmtree(path: Path) -> None:
    """shutil.rmtree that also removes read-only files (git objects on Windows)."""
    def make_writable_and_retry(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=make_writable_and_retry)
    else:
        shutil.rmtree(path, onerror=make_writable_and_retry)


def _check_name(name: str) -> str:
    if not NAME.match(name or ""):
        raise GenomeError(f"invalid name '{name}': use lowercase letters, digits, underscores")
    return name


def check_tool_code(code: str) -> None:
    """Static checks before code is written into the genome."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise GenomeError(f"syntax error: {e}") from e
    has_run = any(isinstance(n, ast.FunctionDef) and n.name == "run" for n in tree.body)
    if not has_run:
        raise GenomeError("code must define a top-level function run(env, **kwargs)")


@dataclass
class ToolMeta:
    name: str
    description: str
    parameters: dict


class Genome:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    # -- lifecycle --------------------------------------------------------
    @classmethod
    def stem(cls, root: Path | str) -> "Genome":
        g = cls(root)
        if g.root.exists():
            rmtree(g.root)
        for sub in ("tools", "skills", "subagents", "hooks"):
            (g.root / sub).mkdir(parents=True, exist_ok=True)
        g._write_meta({"version": 0, "identity": "", "system_prompt": "", "mode": dict(DEFAULT_MODE)})
        g._git("init", "-q")
        g.commit("stem: undifferentiated genome")
        return g

    def copy_to(self, dest: Path | str) -> "Genome":
        dest = Path(dest)
        if dest.exists():
            rmtree(dest)
        shutil.copytree(self.root, dest)
        return Genome(dest)

    # -- metadata ---------------------------------------------------------
    def _meta_path(self) -> Path:
        return self.root / "genome.json"

    def meta(self) -> dict:
        data = json.loads(self._meta_path().read_text(encoding="utf-8"))
        data["mode"] = {**DEFAULT_MODE, **data.get("mode", {})}
        return data

    def _write_meta(self, data: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._meta_path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _update(self, **fields) -> None:
        data = self.meta()
        data.update(fields)
        self._write_meta(data)

    @property
    def identity(self) -> str:
        return self.meta()["identity"]

    @property
    def system_prompt(self) -> str:
        return self.meta()["system_prompt"]

    @property
    def mode(self) -> dict:
        return self.meta()["mode"]

    def set_identity(self, text: str) -> None:
        self._update(identity=text.strip()[:2000])

    def set_system_prompt(self, text: str) -> None:
        self._update(system_prompt=text.strip()[:6000])

    def set_mode(self, **changes) -> dict:
        mode = self.mode
        for key, value in changes.items():
            if value is None:
                continue
            if key == "max_steps":
                mode[key] = max(2, min(int(value), 30))
            elif key == "temperature":
                mode[key] = max(0.0, min(float(value), 1.0))
            elif key == "plan_first":
                mode[key] = bool(value)
            elif key == "reflect_every":
                mode[key] = max(0, min(int(value), 10))
            elif key == "model_tier":
                if value not in MODEL_TIERS:
                    raise GenomeError(f"model_tier must be one of {MODEL_TIERS}")
                mode[key] = value
            else:
                raise GenomeError(f"unknown mode setting '{key}'")
        self._update(mode=mode)
        return mode

    # -- tools ------------------------------------------------------------
    def tools(self) -> list[ToolMeta]:
        out = []
        for meta in sorted((self.root / "tools").glob("*.json")):
            d = json.loads(meta.read_text(encoding="utf-8"))
            out.append(ToolMeta(d["name"], d.get("description", ""), d.get("parameters") or
                                {"type": "object", "properties": {}}))
        return out

    def tool_path(self, name: str) -> Path:
        return self.root / "tools" / f"{_check_name(name)}.py"

    def write_tool(self, name: str, description: str, parameters: dict, code: str) -> None:
        _check_name(name)
        check_tool_code(code)
        if not isinstance(parameters, dict) or parameters.get("type") != "object":
            raise GenomeError('parameters must be a JSON schema object: {"type": "object", "properties": {...}}')
        parameters.setdefault("properties", {})
        (self.root / "tools").mkdir(exist_ok=True)
        self.tool_path(name).write_text(code, encoding="utf-8")
        (self.root / "tools" / f"{name}.json").write_text(json.dumps(
            {"name": name, "description": description.strip()[:600], "parameters": parameters},
            indent=2), encoding="utf-8")

    def delete_tool(self, name: str) -> None:
        for ext in (".py", ".json"):
            (self.root / "tools" / f"{_check_name(name)}{ext}").unlink(missing_ok=True)

    # -- skills -----------------------------------------------------------
    def skills(self) -> dict[str, str]:
        return {p.stem: p.read_text(encoding="utf-8") for p in sorted((self.root / "skills").glob("*.md"))}

    def write_skill(self, name: str, content: str) -> None:
        (self.root / "skills").mkdir(exist_ok=True)
        (self.root / "skills" / f"{_check_name(name)}.md").write_text(content.strip()[:8000] + "\n",
                                                                        encoding="utf-8")

    def delete_skill(self, name: str) -> None:
        (self.root / "skills" / f"{_check_name(name)}.md").unlink(missing_ok=True)

    # -- sub-agents ---------------------------------------------------------
    def subagents(self) -> dict[str, dict]:
        return {p.stem: json.loads(p.read_text(encoding="utf-8"))
                for p in sorted((self.root / "subagents").glob("*.json"))}

    def write_subagent(self, name: str, purpose: str, system_prompt: str, tools: list[str],
                       max_steps: int = 6) -> None:
        (self.root / "subagents").mkdir(exist_ok=True)
        (self.root / "subagents" / f"{_check_name(name)}.json").write_text(json.dumps({
            "name": name, "purpose": purpose.strip()[:300], "system_prompt": system_prompt.strip()[:3000],
            "tools": [t for t in tools if t], "max_steps": max(2, min(int(max_steps), 10))},
            indent=2), encoding="utf-8")

    def delete_subagent(self, name: str) -> None:
        (self.root / "subagents" / f"{_check_name(name)}.json").unlink(missing_ok=True)

    # -- hooks --------------------------------------------------------------
    def hook_path(self, event: str) -> Path | None:
        if event not in HOOK_EVENTS:
            raise GenomeError(f"hook event must be one of {HOOK_EVENTS}")
        p = self.root / "hooks" / f"{event}.py"
        return p if p.exists() else None

    def write_hook(self, event: str, code: str) -> None:
        if event not in HOOK_EVENTS:
            raise GenomeError(f"hook event must be one of {HOOK_EVENTS}")
        check_tool_code(code)
        (self.root / "hooks").mkdir(exist_ok=True)
        (self.root / "hooks" / f"{event}.py").write_text(code, encoding="utf-8")

    def delete_hook(self, event: str) -> None:
        p = self.hook_path(event)
        if p:
            p.unlink()

    # -- inspection ---------------------------------------------------------
    def is_stem(self) -> bool:
        return (not self.identity and not self.system_prompt and not self.tools()
                and not self.skills() and not self.subagents()
                and not any(self.hook_path(e) for e in HOOK_EVENTS))

    def fingerprint(self) -> str:
        h = hashlib.sha256()
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and ".git" not in p.parts:
                h.update(str(p.relative_to(self.root)).encode())
                h.update(p.read_bytes())
        return h.hexdigest()[:12]

    def describe(self, with_code: bool = False) -> str:
        m = self.meta()
        lines = [f"identity: {m['identity'] or '(none yet)'}",
                 f"system_prompt: {m['system_prompt'] or '(none yet)'}",
                 f"mode: {json.dumps(m['mode'])}"]
        tools = self.tools()
        lines.append("tools: " + (", ".join(f"{t.name} - {t.description[:80]}" for t in tools) or "(none)"))
        if with_code:
            for t in tools:
                lines.append(f"--- tools/{t.name}.py ---\n{self.tool_path(t.name).read_text(encoding='utf-8')}")
        skills = self.skills()
        lines.append("skills: " + (", ".join(skills) or "(none)"))
        subs = self.subagents()
        lines.append("subagents: " + (", ".join(f"{k} ({v['purpose'][:60]})" for k, v in subs.items()) or "(none)"))
        hooks = [e for e in HOOK_EVENTS if self.hook_path(e)]
        lines.append("hooks: " + (", ".join(hooks) or "(none)"))
        return "\n".join(lines)

    # -- versioning ---------------------------------------------------------
    def _git(self, *args: str) -> str:
        try:
            out = subprocess.run(["git", "-c", "user.name=stem", "-c", "user.email=stem@localhost",
                                  "-c", "commit.gpgsign=false", *args],
                                 cwd=self.root, capture_output=True, text=True, timeout=30)
            return out.stdout
        except (OSError, subprocess.SubprocessError):
            return ""  # git is optional; snapshots still work without it

    def commit(self, message: str) -> None:
        self._git("add", "-A")
        self._git("commit", "-q", "--allow-empty", "-m", message[:4000])

    def log(self) -> str:
        return self._git("log", "--format=%h %s", "--reverse")
