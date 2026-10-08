"""Command line.

  python -m stem selftest                 offline: sandbox + environments, no API calls
  python -m stem check                    API key, models and tool calling
  python -m stem envs                     environments and their tasks
  python -m stem baseline --env archive   the undifferentiated agent on held-out tasks
  python -m stem grow --env archive       develop a genome (add --resume to continue)
  python -m stem matrix --run runs/a --run runs/b ...   genome x environment on held-out tasks
  python -m stem show --run runs/archive  what a genome became, and how
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .config import Settings
from .envs import REGISTRY, make
from .genome import Genome
from .llm import ChatClient, ConfigError, LLMError, QuotaExhausted, StopRun
from .loop import run_agent
from .sandbox import run_code
from .tools import Tool, ToolSet, schema

REPO = Path(__file__).resolve().parent.parent


def _console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles
        except (AttributeError, ValueError):
            pass


def _logger(path: Path | None):
    fh = path.open("a", encoding="utf-8") if path else None

    def log(msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        if fh:
            fh.write(line + "\n")
            fh.flush()
    return log


def _client(settings: Settings, log) -> ChatClient:
    fallbacks = {}
    if settings.model_develop_fallback and settings.model_develop_fallback != settings.model_develop:
        fallbacks[settings.model_develop] = settings.model_develop_fallback
    return ChatClient(settings.api_base, settings.api_key, settings.token_budget, log=log,
                      fallbacks=fallbacks)


def _usage(client: ChatClient, log) -> None:
    per_model = ", ".join(f"{m}: {n}" for m, n in client.usage.by_model.items()) or "none"
    log(f"tokens used: {client.usage.total} in {client.usage.calls} calls ({per_model})")


# -- commands -----------------------------------------------------------------
def cmd_selftest(args, settings) -> int:
    log = _logger(None)
    ok = True
    for name, cls in REGISTRY.items():
        ref = REPO / "tests" / "reference" / f"{name}_reference.py"
        for split in ("train", "test"):
            for task in cls().tasks(split):
                idle = cls()
                idle.start(task)
                idle_score, _ = idle.score("")
                env = cls()
                env.start(task)
                out, calls = run_code(ref, {"question": task.instruction} if name == "archive" else {},
                                      env.call, timeout=120, max_env_calls=env.max_internal_calls)
                score, note = env.score(out)
                flag = "ok " if idle_score == 0 and score >= 0.4 else "!! "
                ok &= flag == "ok "
                log(f"{flag}{task.id:12s} doing nothing: {idle_score:.2f}   reference tool: {score:.2f} "
                    f"({calls} env calls)  {note[:90]}")
    log("selftest passed: tasks are unsolved by doing nothing and solvable through tools" if ok
        else "selftest found problems (marked !!)")
    return 0 if ok else 1


def cmd_check(args, settings) -> int:
    log = _logger(None)
    log(f"endpoint: {settings.api_base}")
    log(f"models: develop={settings.model_develop} act={settings.model_act} fast={settings.model_fast} "
        f"search={settings.model_search}")
    client = _client(settings, log)
    ok = True
    for tier, model in (("develop", settings.model_develop), ("act", settings.model_act),
                        ("fast", settings.model_fast)):
        seen = {}
        tools = ToolSet([Tool("add", "Add two integers.", schema({"a": {"type": "integer"}, "b": {"type": "integer"}},
                                                                ["a", "b"]),
                              lambda a: seen.setdefault("sum", int(a["a"]) + int(a["b"])))])
        try:
            res = run_agent(client, model, "You are a careful assistant. Use tools.",
                            "Use the add tool to add 19 and 23, then call finish with the result.",
                            tools, max_steps=4, max_tokens=300)
            good = seen.get("sum") == 42 and "42" in res.final
            ok &= good
            log(f"{'ok ' if good else '!! '}{tier:8s} {model}: tool call {'worked' if good else 'did not work'} "
                f"(stopped: {res.stopped}, answer: {res.final[:40]!r}) {res.error}")
        except QuotaExhausted as e:
            ok = False
            log(f"!! {tier:8s} {model}: daily quota exhausted. {e}")
        except ConfigError as e:
            ok = False
            log(f"!! {tier:8s} {model}: not usable with this key. {str(e)[:200]}")
        except LLMError as e:
            ok = False
            log(f"!! {tier:8s} {model}: {e}")
    _usage(client, log)
    return 0 if ok else 1


def cmd_envs(args, settings) -> int:
    for name, cls in REGISTRY.items():
        env = cls()
        print(f"\n== {name} (max {env.max_steps} steps per task)\n{env.brief}")
        for split in ("train", "test"):
            for t in env.tasks(split):
                print(f"  [{split}] {t.id}: {t.instruction[:150]}")
    return 0


def _quota_exit(e: Exception, log, client, hint: str) -> int:
    log(f"\nStopped: {e}")
    if isinstance(e, ConfigError):
        log("This is a configuration problem (API key or model name). Check .env, then "
            "`python -m stem check`. Groq's current models: https://console.groq.com/docs/models")
    else:
        log(f"Progress is saved. When the quota resets (Groq: midnight UTC) or after raising "
            f"STEM_TOKEN_BUDGET, run the same command{hint} to continue.")
    _usage(client, log)
    return 3


def cmd_grow(args, settings) -> int:
    from .evolve import grow, summary_table
    run_dir = Path(args.run) if args.run else settings.runs_dir / args.env
    run_dir.mkdir(parents=True, exist_ok=True)
    log = _logger(run_dir / "log.txt")
    client = _client(settings, log)
    env_cls = type(make(args.env))
    try:
        records = grow(env_cls, settings, client, run_dir, generations=args.generations,
                       dev_steps=args.dev_steps, trials=args.trials, resume=args.resume,
                       train_limit=args.train_tasks, log=log)
    except StopRun as e:
        return _quota_exit(e, log, client, " with --resume")
    log("\n" + summary_table(records))
    log(f"genome: {run_dir / 'genome'}  (history: python -m stem show --run {run_dir})")
    _usage(client, log)
    return 0


def cmd_baseline(args, settings) -> int:
    from .evaluate import matrix, render
    out = Path(args.out)
    log = _logger(None)
    client = _client(settings, log)
    envs = [type(make(n)) for n in (args.env or list(REGISTRY))]
    try:
        table = matrix({}, envs, args.split, client, settings, out, log)
    except StopRun as e:
        return _quota_exit(e, log, client, "")
    log("\n" + render(table, [e.name for e in envs], args.split))
    _usage(client, log)
    return 0


def cmd_matrix(args, settings) -> int:
    from .evaluate import matrix, render
    out = Path(args.out)
    log = _logger(None)
    genomes = {}
    for r in args.run:
        meta = json.loads((Path(r) / "run.json").read_text(encoding="utf-8"))
        genomes[f"grown in {meta['environment']}"] = Path(r) / "genome"
    envs = [type(make(n)) for n in (args.env or list(REGISTRY))]
    client = _client(settings, log)
    try:
        table = matrix(genomes, envs, args.split, client, settings, out, log)
    except StopRun as e:
        return _quota_exit(e, log, client, "")
    log("\n" + render(table, [e.name for e in envs], args.split))
    log(f"saved to {out / 'matrix.md'} and {out / 'matrix.json'}")
    _usage(client, log)
    return 0


def cmd_show(args, settings) -> int:
    g = Genome(Path(args.run) / "genome")
    print(g.describe(with_code=args.code))
    skills = g.skills()
    for name, text in skills.items():
        print(f"\n--- skills/{name}.md ---\n{text}")
    print("\nlineage (git log inside the genome):")
    print(g.log() or "(git not available)")
    gens = Path(args.run) / "generations.jsonl"
    if gens.exists():
        from .evolve import Generation, summary_table
        print("\n" + summary_table([Generation(**json.loads(l)) for l in gens.read_text(encoding="utf-8").splitlines() if l]))
    return 0


def main(argv: list[str] | None = None) -> int:
    _console()
    p = argparse.ArgumentParser(prog="python -m stem", description="Stem agent v2")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest", help="offline check of sandbox and environments")
    sub.add_parser("check", help="check API key, models and tool calling")
    sub.add_parser("envs", help="list environments and tasks")

    g = sub.add_parser("grow", help="develop a genome in one environment")
    g.add_argument("--env", required=True, choices=list(REGISTRY))
    g.add_argument("--generations", type=int, default=3)
    g.add_argument("--dev-steps", type=int, default=12, help="steps of development per generation")
    g.add_argument("--trials", type=int, default=1, help="run_trial calls allowed per generation")
    g.add_argument("--train-tasks", type=int, help="use only the first N training tasks (saves quota)")
    g.add_argument("--run", help="run directory (default runs/<env>)")
    g.add_argument("--resume", action="store_true", help="continue an interrupted run")

    b = sub.add_parser("baseline", help="the undifferentiated agent on held-out tasks")
    b.add_argument("--env", action="append", choices=list(REGISTRY))
    b.add_argument("--split", default="test", choices=["train", "test"])
    b.add_argument("--out", default="runs/eval")

    m = sub.add_parser("matrix", help="grown genomes x environments on held-out tasks")
    m.add_argument("--run", action="append", required=True)
    m.add_argument("--env", action="append", choices=list(REGISTRY))
    m.add_argument("--split", default="test", choices=["train", "test"])
    m.add_argument("--out", default="runs/eval")

    s = sub.add_parser("show", help="inspect a grown genome")
    s.add_argument("--run", required=True)
    s.add_argument("--code", action="store_true")

    args = p.parse_args(argv)
    settings = Settings.from_env()
    handler = {"selftest": cmd_selftest, "check": cmd_check, "envs": cmd_envs, "grow": cmd_grow,
               "baseline": cmd_baseline, "matrix": cmd_matrix, "show": cmd_show}[args.cmd]
    try:
        return handler(args, settings)
    except LLMError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
