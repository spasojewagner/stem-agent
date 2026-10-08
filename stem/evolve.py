"""Grow a stem genome inside one environment.

generation 0   the undifferentiated genome is scored on the training tasks
generation g   copy the best genome -> development rewrites the copy ->
               score the copy on all training tasks -> keep it only if it
               beats the best so far (or, while nothing scores above zero,
               if it changed anything at all, so early groundwork is not lost)

Everything is written to disk after each generation, so a run interrupted by
a daily quota can be resumed with --resume.
"""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean
from typing import Any, Callable

from .develop import Evidence, develop
from .genome import Genome, rmtree
from .phenotype import Outcome, run_task, to_record


@dataclass
class Generation:
    generation: int
    accepted: bool
    train_score: float
    per_task: dict
    summary: str
    fingerprint: str
    tokens_used: int
    seconds: float


def evaluate_genome(genome: Genome, env_cls: type, split: str, client: Any, settings: Any,
                    log: Callable[[str], None], limit: int | None = None) -> tuple[float, list[Outcome]]:
    outcomes = []
    tasks = env_cls().tasks(split)
    for task in tasks[:limit] if limit else tasks:
        log(f"  task {task.id} ...")
        out = run_task(genome, env_cls(), task, client, settings, log=log)
        log(f"  -> {out.summary()}")
        outcomes.append(out)
    return (fmean(o.score for o in outcomes) if outcomes else 0.0), outcomes


def _latest_lines(outcomes: list[Outcome]) -> list[str]:
    lines = []
    for o in outcomes:
        lines.append(f"- {o.summary()}")
        lines += ["    " + l for l in o.run.digest(max_lines=6, width=110).splitlines()]
    return lines


def grow(env_cls: type, settings: Any, client: Any, run_dir: Path, generations: int = 3,
         dev_steps: int = 12, trials: int = 1, resume: bool = False, train_limit: int | None = None,
         log: Callable[[str], None] = print) -> list[Generation]:
    run_dir.mkdir(parents=True, exist_ok=True)
    best = Genome(run_dir / "genome")
    gen_file = run_dir / "generations.jsonl"
    records: list[Generation] = []

    if resume and gen_file.exists() and best.root.exists():
        records = [Generation(**json.loads(l)) for l in gen_file.read_text(encoding="utf-8").splitlines() if l]
        log(f"resuming {run_dir} after generation {records[-1].generation}")
    else:
        if gen_file.exists():
            gen_file.unlink()
        Genome.stem(best.root)
        (run_dir / "run.json").write_text(json.dumps({
            "environment": env_cls.name, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "models": {"develop": settings.model_develop, "act": settings.model_act,
                       "fast": settings.model_fast}}, indent=2), encoding="utf-8")

    def save(rec: Generation, outcomes: list[Outcome]) -> None:
        records.append(rec)
        with gen_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
        (run_dir / f"train_g{rec.generation:03d}.json").write_text(
            json.dumps([to_record(o) for o in outcomes], ensure_ascii=False, indent=2), encoding="utf-8")

    latest: list[str] = []
    if not records:
        log(f"generation 0: scoring the undifferentiated genome on {env_cls.name} training tasks")
        t0, tok0 = time.time(), client.usage.total
        score, outs = evaluate_genome(best, env_cls, "train", client, settings, log, train_limit)
        save(Generation(0, True, score, {o.task_id: o.score for o in outs}, "undifferentiated baseline",
                        best.fingerprint(), client.usage.total - tok0, round(time.time() - t0, 1)), outs)
        latest = _latest_lines(outs)
    else:
        last_file = run_dir / f"train_g{max(r.generation for r in records if r.accepted):03d}.json"
        if last_file.exists():
            for rec in json.loads(last_file.read_text(encoding="utf-8")):
                latest.append(f"- {rec['task']}: score {rec['score']:.2f} ({rec['note']})")
                latest += ["    " + l for l in rec["digest"].splitlines()[:7]]

    best_score = max(r.train_score for r in records if r.accepted)
    history = [f"- g{r.generation}: {'kept' if r.accepted else 'discarded'}, training score "
               f"{r.train_score:.2f}. {r.summary[:240]}" for r in records[1:]]

    start = records[-1].generation + 1
    for g in range(start, start + generations):   # `generations` more, also when resuming
        t0, tok0 = time.time(), client.usage.total
        cand_dir = run_dir / "candidates" / f"g{g:03d}"
        summary_file = run_dir / "candidates" / f"g{g:03d}.summary.txt"
        failed = False
        if resume and cand_dir.exists() and summary_file.exists():
            log(f"\ngeneration {g}: reusing the development finished before the interruption")
            cand, summary = Genome(cand_dir), summary_file.read_text(encoding="utf-8")
        else:
            log(f"\ngeneration {g}: development")
            cand = best.copy_to(cand_dir)
            dev = develop(cand, env_cls, client, settings, Evidence(g, best_score, latest, history),
                          max_steps=dev_steps, max_trials=trials, train_limit=train_limit, log=log)
            summary, failed = dev.summary, dev.failed
            if not failed:
                summary_file.write_text(summary, encoding="utf-8")
        log(f"development summary: {summary[:400]}")
        changed = cand.fingerprint() != best.fingerprint()
        if failed:
            log("development ended with an error; the candidate is discarded without evaluation")
            score, outs, changed = 0.0, [], False
        elif not changed:
            log("development changed nothing; skipping evaluation")
            score, outs = best_score, []
        else:
            log(f"generation {g}: scoring the candidate on training tasks")
            score, outs = evaluate_genome(cand, env_cls, "train", client, settings, log, train_limit)
        accepted = changed and (score > best_score + 1e-9 or (best_score == 0.0 and score == 0.0))
        rec = Generation(g, accepted, score, {o.task_id: o.score for o in outs}, summary,
                         cand.fingerprint(), client.usage.total - tok0, round(time.time() - t0, 1))
        if accepted:
            cand.commit(f"g{g}: training score {score:.2f}\n\n{summary}")
            rmtree(best.root)
            shutil.copytree(cand.root, best.root)
            best_score = max(best_score, score)
            latest = _latest_lines(outs)
            log(f"generation {g}: KEPT (training score {score:.2f})")
        else:
            log(f"generation {g}: discarded (training score {score:.2f}, best {best_score:.2f})")
        history.append(f"- g{g}: {'kept' if accepted else 'discarded'}, training score {score:.2f}. "
                       f"{summary[:240]}")
        save(rec, outs)
    return records


def summary_table(records: list[Generation]) -> str:
    rows = ["| gen | kept | train score | tokens | summary |", "|---|---|---|---|---|"]
    for r in records:
        rows.append(f"| {r.generation} | {'yes' if r.accepted else 'no'} | {r.train_score:.2f} | "
                    f"{r.tokens_used} | {r.summary[:90].replace('|', '/')} |")
    return "\n".join(rows)
