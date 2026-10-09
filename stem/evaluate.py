"""Does the agent actually differentiate?

The main measurement is a matrix: rows are genomes (the undifferentiated
stem, and one genome grown in each environment), columns are environments,
cells are mean scores on held-out tasks. What we want to see:

  - the stem row is close to zero everywhere (it can't do anything yet),
  - the diagonal is high (each genome became good at its own environment),
  - off-diagonal cells stay low (a genome that became one thing did not
    become everything; the same code grew into different agents).

Results are cached per (genome fingerprint, environment, task), so a run
cut short by a daily quota resumes where it stopped.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import fmean
from typing import Any, Callable

from .genome import Genome
from .phenotype import run_task, to_record


def score_genome(genome: Genome, env_cls: type, split: str, client: Any, settings: Any,
                 cache_dir: Path, log: Callable[[str], None]) -> tuple[float, list[dict]]:
    fp = genome.fingerprint()
    records = []
    for task in env_cls().tasks(split):
        cache = cache_dir / fp / env_cls.name / f"{task.id}.json"
        if cache.exists():
            rec = json.loads(cache.read_text(encoding="utf-8"))
            log(f"  {task.id}: {rec['score']:.2f} (cached)")
        else:
            out = run_task(genome, env_cls(), task, client, settings, log=log)
            rec = to_record(out)
            if out.run.stopped == "error":  # technical failure: report it, but measure again next time
                log(f"  {task.id}: not cached, the episode failed: {out.run.error[:200]}")
            else:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"  {task.id}: {rec['score']:.2f} - {rec['note']}")
        records.append(rec)
    return (fmean(r["score"] for r in records) if records else 0.0), records


def matrix(genomes: dict[str, Path], env_classes: list[type], split: str, client: Any, settings: Any,
           out_dir: Path, log: Callable[[str], None] = print) -> dict[str, dict[str, float]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem_dir = out_dir / "stem_genome"
    if not stem_dir.exists():
        Genome.stem(stem_dir)
    rows = {"stem (undifferentiated)": stem_dir, **genomes}
    table: dict[str, dict[str, float]] = {}
    details: dict[str, dict[str, list[dict]]] = {}
    for label, path in rows.items():
        g = Genome(path)
        table[label], details[label] = {}, {}
        for env_cls in env_classes:
            log(f"\n[{label}] on {env_cls.name} ({split})")
            mean, recs = score_genome(g, env_cls, split, client, settings, out_dir / "cache", log)
            table[label][env_cls.name] = round(mean, 3)
            details[label][env_cls.name] = recs
    (out_dir / "matrix.json").write_text(json.dumps({"split": split, "table": table, "details": details},
                                                    ensure_ascii=False, indent=2), encoding="utf-8")
    md = render(table, [e.name for e in env_classes], split)
    (out_dir / "matrix.md").write_text(md, encoding="utf-8")
    return table


def render(table: dict[str, dict[str, float]], envs: list[str], split: str) -> str:
    head = "| genome | " + " | ".join(envs) + " |"
    sep = "|---|" + "---|" * len(envs)
    lines = [f"Mean score on {split} tasks", "", head, sep]
    for label, row in table.items():
        lines.append(f"| {label} | " + " | ".join(f"{row.get(e, float('nan')):.2f}" for e in envs) + " |")
    return "\n".join(lines) + "\n"
