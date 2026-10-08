"""Express a genome as a working agent inside an environment.

The phenotype can only use what the genome gives it plus the environment's
raw actions. It cannot change its own genome; that happens only during
development (see develop.py).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from .genome import Genome
from .llm import reasoning_extra
from .loop import RunResult, run_agent
from .sandbox import run_code
from .tools import Tool, ToolSet, schema

UNDIFFERENTIATED = ("You have not developed into anything yet: no identity, no procedures, "
                    "no tools of your own.")


@dataclass
class Outcome:
    task_id: str
    score: float
    note: str
    run: RunResult

    def summary(self) -> str:
        return f"{self.task_id}: score {self.score:.2f} ({self.note})"


def env_tools(env: Any) -> list[Tool]:
    """The environment's raw actions as tools. Each call costs the agent one step."""
    out = []
    for a in env.actions():
        out.append(Tool(a.name, a.description, a.parameters,
                        (lambda name: lambda args: env.call(name, args))(a.name)))
    return out


def genome_tools(genome: Genome, env: Any, timeout: int) -> list[Tool]:
    out = []
    for meta in genome.tools():
        path = genome.tool_path(meta.name)

        def fn(args: dict, _path=path) -> str:
            text, _calls = run_code(_path, args, env.call, timeout=timeout,
                                    max_env_calls=env.max_internal_calls)
            return text
        out.append(Tool(meta.name, meta.description + " (one of your own tools)", meta.parameters, fn))
    return out


def system_prompt(genome: Genome, env: Any, max_steps: int) -> str:
    m = genome.meta()
    parts = ["# Who you are", m["identity"] or UNDIFFERENTIATED, "",
             "# Where you are",
             f"You are working inside an environment called '{env.name}'. {env.brief}",
             f"You act only through tool calls. You have at most {max_steps} steps for this task; "
             "each tool call is one step. Your work is graded by the environment from what you "
             "actually did and answered, not from what you say you did.", ""]
    skills = genome.skills()
    subs = genome.subagents()
    if m["system_prompt"] or skills or subs:
        parts.append("# How you work")
        if m["system_prompt"]:
            parts.append(m["system_prompt"])
        if skills:
            parts.append("Procedures you wrote for yourself (read one with read_skill): " + ", ".join(skills))
        if subs:
            parts.append("Specialists you can delegate to with delegate(name, instruction): " +
                         "; ".join(f"{k}: {v['purpose']}" for k, v in subs.items()))
        parts.append("")
    if m["mode"].get("plan_first"):
        parts.append("Before your first tool call, write a short plan in your message.")
    parts.append("When you are done, call finish(answer).")
    return "\n".join(parts)


def build_toolset(genome: Genome, env: Any, client: Any, settings: Any,
                  log: Callable[[str], None] | None = None) -> ToolSet:
    ts = ToolSet(env_tools(env) + genome_tools(genome, env, settings.tool_timeout))
    skills = genome.skills()
    if skills:
        ts.add(Tool("read_skill", "Read one of your written procedures.",
                    schema({"name": {"type": "string", "enum": list(skills)}}, ["name"]),
                    lambda a: skills.get(a.get("name", ""), f"no skill named {a.get('name')}")))
    subs = genome.subagents()
    if subs:
        def delegate(args: dict) -> str:
            spec = subs.get(args.get("name", ""))
            if not spec:
                return f"no specialist named {args.get('name')}. Available: {', '.join(subs)}"
            allowed = set(spec.get("tools") or [])
            sub_ts = ToolSet([t for t in env_tools(env) + genome_tools(genome, env, settings.tool_timeout)
                              if not allowed or t.name in allowed])
            res = run_agent(client, settings.model_fast, spec["system_prompt"] +
                            f"\n\nYou work inside '{env.name}'. {env.brief}\nReport back with finish(answer).",
                            str(args.get("instruction", "")), sub_ts, max_steps=int(spec.get("max_steps", 6)),
                            log=log, extra=reasoning_extra(settings.model_fast, settings.reasoning_act))
            return f"[{spec['name']}] {res.final or '(no answer)'}"
        ts.add(Tool("delegate", "Hand a sub-task to one of your specialists and get its answer back.",
                    schema({"name": {"type": "string", "enum": list(subs)},
                            "instruction": {"type": "string"}}, ["name", "instruction"]), delegate))
    return ts


def run_task(genome: Genome, env: Any, task: Any, client: Any, settings: Any,
             log: Callable[[str], None] | None = None) -> Outcome:
    env.start(task)
    mode = genome.mode
    max_steps = min(int(mode["max_steps"]), env.max_steps)
    user = f"Task: {task.instruction}"

    start_hook = genome.hook_path("on_task_start")
    if start_hook:
        extra, _ = run_code(start_hook, {"task": task.instruction}, env.call,
                            timeout=settings.tool_timeout, max_env_calls=env.max_internal_calls)
        user += f"\n\nContext prepared by your on_task_start hook:\n{extra[:2500]}"

    finish_hook = genome.hook_path("on_finish")

    def on_finish(answer: str) -> str | None:
        if not finish_hook:
            return None
        verdict, _ = run_code(finish_hook, {"answer": answer}, env.call,
                              timeout=settings.tool_timeout, max_env_calls=env.max_internal_calls)
        verdict = verdict.strip()
        if verdict.startswith("TOOL ERROR"):
            if log:
                log(f"  on_finish hook failed, accepting the answer: {verdict[:200]}")
            return None
        return verdict if verdict and verdict.lower() not in {"ok", "accept", "\"\"", "null"} else None

    tools = build_toolset(genome, env, client, settings, log)
    model = settings.model_for(mode["model_tier"])
    run = run_agent(client, model, system_prompt(genome, env, max_steps),
                    user, tools, max_steps=max_steps, temperature=float(mode["temperature"]),
                    on_finish=on_finish, reflect_every=int(mode["reflect_every"]), log=log,
                    extra=reasoning_extra(model, settings.reasoning_act))
    score, note = env.score(run.final)
    return Outcome(task.id, score, note, run)


def to_record(o: Outcome) -> dict:
    return {"task": o.task_id, "score": o.score, "note": o.note, "stopped": o.run.stopped,
            "steps": len(o.run.steps), "final": o.run.final[:500], "digest": o.run.digest()}


def dumps(o: Outcome) -> str:
    return json.dumps(to_record(o), ensure_ascii=False, indent=2)
