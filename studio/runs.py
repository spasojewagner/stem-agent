"""Read-only views of what the command line writes under runs/.

    runs/<name>/run.json            environment, creation time, models
    runs/<name>/generations.jsonl   one record per generation
    runs/<name>/train_gNNN.json     task outcomes of each scored generation
    runs/<name>/notebook.jsonl      notes development wrote for itself
    runs/<name>/genome/             the best genome (a git repository)
    runs/<name>/candidates/gNNN/    what each generation's development produced
    runs/eval/matrix.json           genomes x environments on held-out tasks
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from stem.genome import HOOK_EVENTS, Genome

RUN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
MAX_DIFF_CHARS = 200_000


class NotFound(LookupError):
    pass


def run_dir(runs_dir: Path, name: str) -> Path:
    """The folder of one run. Names are checked, so a request can never reach outside runs/."""
    if not RUN_NAME.match(name or "") or name in {".", ".."}:
        raise NotFound(f"no run named {name!r}")
    path = (runs_dir / name).resolve()
    if path.parent != runs_dir.resolve() or not (path / "run.json").is_file():
        raise NotFound(f"no run named {name!r}")
    return path


def _jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue  # a line cut short by an interruption
    return out


def generations(path: Path) -> list[dict]:
    return _jsonl(path / "generations.jsonl")


def notebook(path: Path) -> list[dict]:
    return [{"generation": n.get("generation"), "text": str(n.get("text", ""))}
            for n in _jsonl(path / "notebook.jsonl")]


def summarize(path: Path, active: bool = False) -> dict:
    meta = json.loads((path / "run.json").read_text(encoding="utf-8"))
    gens = generations(path)
    kept = [g for g in gens if g.get("accepted")]
    gen_file = path / "generations.jsonl"
    return {
        "name": path.name,
        "environment": meta.get("environment", ""),
        "created": meta.get("created", ""),
        "models": meta.get("models", {}),
        "generations": len(gens),
        "kept": max(len(kept) - 1, 0),             # generation 0 is the baseline, not a change
        "best_score": max((g["train_score"] for g in kept), default=0.0),
        "baseline_score": gens[0]["train_score"] if gens else None,
        "tokens": sum(int(g.get("tokens_used", 0)) for g in gens),
        "scores": [{"generation": g["generation"], "score": g["train_score"], "accepted": g["accepted"]}
                   for g in gens],
        "updated": gen_file.stat().st_mtime if gen_file.exists() else (path / "run.json").stat().st_mtime,
        "active": active,
    }


def list_runs(runs_dir: Path, active: set[str] = frozenset()) -> list[dict]:
    if not runs_dir.is_dir():
        return []
    out = []
    for p in runs_dir.iterdir():
        if p.is_dir() and RUN_NAME.match(p.name) and (p / "run.json").is_file():
            try:
                out.append(summarize(p, p.name in active))
            except (ValueError, KeyError, OSError):
                continue  # half-written run.json
    return sorted(out, key=lambda r: r["updated"], reverse=True)


def genome_view(genome: Genome) -> dict:
    meta = genome.meta()
    tools = []
    for t in genome.tools():
        code_path = genome.tool_path(t.name)
        tools.append({"name": t.name, "description": t.description, "parameters": t.parameters,
                      "code": code_path.read_text(encoding="utf-8") if code_path.exists() else ""})
    hooks = []
    for event in HOOK_EVENTS:
        p = genome.hook_path(event)
        if p:
            hooks.append({"event": event, "code": p.read_text(encoding="utf-8")})
    return {
        "identity": meta.get("identity", ""),
        "system_prompt": meta.get("system_prompt", ""),
        "mode": meta.get("mode", {}),
        "tools": tools,
        "skills": [{"name": k, "content": v} for k, v in genome.skills().items()],
        "subagents": list(genome.subagents().values()),
        "hooks": hooks,
        "fingerprint": genome.fingerprint(),
        "is_stem": genome.is_stem(),
    }


def genome_for(path: Path, generation: int | None = None) -> Genome:
    """The best genome, or the candidate a given generation's development produced."""
    if generation is None:
        root = path / "genome"
    else:
        root = path / "candidates" / f"g{generation:03d}"
    if not (root / "genome.json").is_file():
        raise NotFound("no genome for this generation" if generation is not None else "no genome yet")
    return Genome(root)


def outcomes(path: Path, generation: int) -> list[dict]:
    f = path / f"train_g{generation:03d}.json"
    if not f.is_file():
        raise NotFound(f"generation {generation} has no scored tasks")
    return json.loads(f.read_text(encoding="utf-8"))


def _git(root: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=root, capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout if out.returncode == 0 else ""


def lineage(genome: Genome) -> list[dict]:
    """Every accepted change, oldest first, with the files it touched."""
    raw = _git(genome.root, "log", "--reverse", "--date=iso-strict", "--numstat",
               "--format=\x1e%H\x1f%h\x1f%ad\x1f%s\x1f%b\x1f")
    commits = []
    for block in raw.split("\x1e"):
        if not block.strip():
            continue
        sha, short, date, subject, body, rest = (block.split("\x1f") + [""] * 6)[:6]
        files = []
        for line in rest.strip().splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                added, removed, name = parts
                files.append({"path": name, "added": int(added) if added.isdigit() else 0,
                              "removed": int(removed) if removed.isdigit() else 0})
        commits.append({"sha": sha, "short": short, "date": date, "subject": subject,
                        "body": body.strip(), "files": files})
    return commits


def commit_diff(genome: Genome, sha: str) -> str:
    if not COMMIT.match(sha or ""):
        raise NotFound("not a commit id")
    diff = _git(genome.root, "show", "--format=", "--patch", "--no-color", sha)
    if not diff and not _git(genome.root, "cat-file", "-t", sha).strip() == "commit":
        raise NotFound(f"no commit {sha}")
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + f"\n... diff cut at {MAX_DIFF_CHARS} characters\n"
    return diff


def eval_matrix(runs_dir: Path) -> dict[str, Any] | None:
    f = runs_dir / "eval" / "matrix.json"
    if not f.is_file():
        return None
    data = json.loads(f.read_text(encoding="utf-8"))
    details = data.get("details", {})
    return {
        "split": data.get("split", "test"),
        "table": data.get("table", {}),
        "details": {genome: {env: [{"task": r.get("task"), "score": r.get("score"), "note": r.get("note")}
                                   for r in recs] for env, recs in envs.items()}
                    for genome, envs in details.items()},
        "updated": f.stat().st_mtime,
    }
