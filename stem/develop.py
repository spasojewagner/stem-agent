"""Development: the stem agent's only built-in capability.

A developmental episode looks at the environment the agent has been placed
in, decides what the agent has to become there, and rewrites the genome:
identity, working instructions, behaviour mode, its own tools, procedures,
specialists and hooks. It never sees held-out tasks.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from .genome import HOOK_EVENTS, MODEL_TIERS, Genome, GenomeError
from .llm import reasoning_extra
from .loop import RunResult, run_agent
from .phenotype import run_task
from .sandbox import run_code
from .tools import Tool, ToolSet, clip, schema
from .web import web_tools

DEVELOPER_PROMPT = """# Who you are
You are the developmental process of a stem agent. The agent has no built-in purpose: it starts undifferentiated and becomes whatever the place it is put in requires. Its genome is the only thing that persists between tasks, and you are the only one who can change it. You are not the agent that does the tasks; you shape it.

# Where you are
The agent has been placed in an environment called '{env_name}'.
{env_brief}
Its raw actions there:
{actions}
The agent gets at most {max_steps} tool calls per task. Raw actions cost one call each. Tools in the genome run as code and may call environment actions many times within a single call, through `env.<action>(...)` with the arguments listed above; each returns exactly what the action returns.

Training tasks you may study and try:
{train_tasks}
Held-out tasks of the same kind, which you will never see, decide whether this works. Build capability that would carry over to new tasks of this kind. Answers or facts that only fit one training task are worthless.

# What you can change
- identity: who the agent is, in its own words, and what success means for it here.
- system_prompt: how it works: priorities, order of work, how to check itself.
- mode: max_steps (2-30), temperature (0-1), plan_first, reflect_every, model_tier ({tiers}).
- tools: Python files defining run(env, **kwargs) and returning a string or JSON-serialisable value. They run in a separate process with the standard library only and no network. Test them before relying on them.
- skills: written procedures the agent can read while working.
- subagents: specialists with their own instructions and a subset of tools.
- hooks: on_task_start(env, task) returns context added to the task; on_finish(env, answer) returns "" to accept the answer or a reason to keep working. Same code rules as tools; define run(env, **kwargs).

# The genome as it is now
{genome}

# What has happened so far
{evidence}

# How to work
Decide first what this agent must become here, then make the changes that get it there. Look at the environment yourself (probe) before you assume how it behaves. Prefer a few changes you have tested over many you have not. run_trial runs the agent on one training task with the genome as it is at that moment, and costs real budget; you have {trials} trial(s). When you are done, call finish with a short account of what you changed and why. The genome is then scored on all training tasks and kept only if it does better than the best genome so far."""


@dataclass
class Evidence:
    generation: int
    best_score: float
    latest: list[str] = field(default_factory=list)   # per-task lines with digests
    history: list[str] = field(default_factory=list)  # one line per earlier generation

    def render(self) -> str:
        lines = [f"Generation {self.generation}. Best mean training score so far: {self.best_score:.2f}."]
        if self.latest:
            lines.append("Latest training results of the current genome:")
            lines += self.latest
        if self.history:
            lines.append("Earlier generations:")
            lines += self.history[-6:]
        return "\n".join(lines)


def _as_obj(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


@dataclass
class DevResult:
    summary: str
    run: RunResult
    trials: list[str]

    @property
    def failed(self) -> bool:
        return self.run.stopped == "error"


def develop(genome: Genome, env_cls: type, client: Any, settings: Any, evidence: Evidence,
            max_steps: int = 12, max_trials: int = 1, train_limit: int | None = None,
            log: Callable[[str], None] | None = None) -> DevResult:
    log = log or (lambda _m: None)
    env = env_cls()
    train = env.tasks("train")[:train_limit] if train_limit else env.tasks("train")
    train_ids = [t.id for t in train]
    scratch = env_cls()
    scratch.start(train[0])
    trials: list[str] = []

    def task(task_id: str | None):
        if not task_id:
            return train[0]
        for t in train:
            if t.id == task_id:
                return t
        raise ValueError(f"unknown training task '{task_id}'. Training tasks: {train_ids}")

    # -- environment access ----------------------------------------------------
    def probe(a: dict) -> Any:
        if a.get("task_id"):
            scratch.start(task(a["task_id"]))
        args = _as_obj(a.get("args"))
        if not isinstance(args, dict):  # also accept {"action": "search", "query": "..."}
            args = {k: v for k, v in a.items() if k not in ("action", "args", "task_id")}
        return scratch.call(str(a.get("action", "")), args)

    def run_trial(a: dict) -> str:
        if len(trials) >= max_trials:
            return f"no trials left ({max_trials} used)"
        t = task(a.get("task_id"))
        out = run_task(genome, env_cls(), t, client, settings, log=log)
        line = f"{out.summary()}\n{out.run.digest(max_lines=10)}"
        trials.append(line)
        return line

    def test_tool(a: dict) -> str:
        name = str(a.get("name", ""))
        try:
            path = genome.tool_path(name)
        except GenomeError as e:
            return f"ERROR: {e}"
        if not path.exists():
            return f"ERROR: no tool named {name}"
        e2 = env_cls()
        e2.start(task(a.get("task_id")))
        out, calls = run_code(path, _as_obj(a.get("args")) or {}, e2.call,
                              timeout=settings.tool_timeout, max_env_calls=e2.max_internal_calls)
        score, note = e2.score(out)
        return clip(f"output: {out}", 1800) + f"\n[{calls} environment calls; environment score " \
                                               f"if the agent stopped here and answered with this output: {score:.2f} ({note})]"

    # -- genome edits ----------------------------------------------------------
    def guarded(fn: Callable[[dict], str]) -> Callable[[dict], str]:
        def inner(a: dict) -> str:
            try:
                return fn(a)
            except (GenomeError, ValueError, TypeError) as e:
                return f"ERROR: {e}"
        return inner

    def write_tool(a: dict) -> str:
        params = _as_obj(a.get("parameters")) or {"type": "object", "properties": {}}
        genome.write_tool(str(a.get("name", "")), str(a.get("description", "")), params, str(a.get("code", "")))
        return f"tool {a.get('name')} saved. Test it with test_tool."

    def write_subagent(a: dict) -> str:
        tools = _as_obj(a.get("tools")) or []
        if isinstance(tools, str):
            tools = [t.strip() for t in tools.split(",")]
        genome.write_subagent(str(a.get("name", "")), str(a.get("purpose", "")),
                              str(a.get("system_prompt", "")), list(tools), int(a.get("max_steps", 6)))
        return f"subagent {a.get('name')} saved"

    def set_mode(a: dict) -> str:
        return "mode is now " + json.dumps(genome.set_mode(**{k: a.get(k) for k in
                                                              ("max_steps", "temperature", "plan_first",
                                                               "reflect_every", "model_tier")}))

    s = lambda props, req=(): schema(props, list(req))
    string = {"type": "string"}
    tools = ToolSet([
        Tool("probe", "Call one environment action directly to see what it returns, e.g. "
                      '{"action": "read", "args": {"doc_id": "D001"}}. Optionally restart on a training task first.',
             s({"action": string, "args": {"type": "object"}, "task_id": string}, ["action"]), probe),
        Tool("run_trial", "Run the agent with the current genome on one training task. Returns its score and what it did.",
             s({"task_id": string}, ["task_id"]), run_trial),
        Tool("view_genome", "Show the genome, optionally with the code of every tool.",
             s({"with_code": {"type": "boolean"}}), lambda a: genome.describe(bool(a.get("with_code")))),
        Tool("set_identity", "Set who the agent is and what success means for it here.",
             s({"text": string}, ["text"]), guarded(lambda a: (genome.set_identity(a["text"]), "identity saved")[1])),
        Tool("set_system_prompt", "Set the agent's working instructions.",
             s({"text": string}, ["text"]), guarded(lambda a: (genome.set_system_prompt(a["text"]), "system prompt saved")[1])),
        Tool("set_mode", "Change behaviour settings. Omit what you do not want to change.",
             s({"max_steps": {"type": "integer"}, "temperature": {"type": "number"},
                "plan_first": {"type": "boolean"}, "reflect_every": {"type": "integer"},
                "model_tier": {"type": "string", "enum": list(MODEL_TIERS)}}), guarded(set_mode)),
        Tool("write_tool", "Create or replace a tool. `code` must define run(env, **kwargs). "
                           "`parameters` is a JSON schema object for the kwargs.",
             s({"name": string, "description": string, "parameters": {"type": "object"}, "code": string},
               ["name", "description", "code"]), guarded(write_tool)),
        Tool("test_tool", "Run one of the genome's tools on a fresh copy of a training task.",
             s({"name": string, "args": {"type": "object"}, "task_id": string}, ["name"]), test_tool),
        Tool("delete_tool", "Remove a tool.", s({"name": string}, ["name"]),
             guarded(lambda a: (genome.delete_tool(a["name"]), "deleted")[1])),
        Tool("write_skill", "Create or replace a written procedure.", s({"name": string, "content": string},
                                                                         ["name", "content"]),
             guarded(lambda a: (genome.write_skill(a["name"], a["content"]), "skill saved")[1])),
        Tool("delete_skill", "Remove a skill.", s({"name": string}, ["name"]),
             guarded(lambda a: (genome.delete_skill(a["name"]), "deleted")[1])),
        Tool("write_subagent", "Create or replace a specialist the agent can delegate to. "
                               "`tools` lists tool names it may use (empty = all).",
             s({"name": string, "purpose": string, "system_prompt": string,
                "tools": {"type": "array", "items": string}, "max_steps": {"type": "integer"}},
               ["name", "purpose", "system_prompt"]), guarded(write_subagent)),
        Tool("delete_subagent", "Remove a specialist.", s({"name": string}, ["name"]),
             guarded(lambda a: (genome.delete_subagent(a["name"]), "deleted")[1])),
        Tool("write_hook", f"Create or replace a hook. event is one of {list(HOOK_EVENTS)}.",
             s({"event": {"type": "string", "enum": list(HOOK_EVENTS)}, "code": string}, ["event", "code"]),
             guarded(lambda a: (genome.write_hook(a["event"], a["code"]), "hook saved")[1])),
        Tool("delete_hook", "Remove a hook.", s({"event": {"type": "string", "enum": list(HOOK_EVENTS)}}, ["event"]),
             guarded(lambda a: (genome.delete_hook(a["event"]), "deleted")[1])),
    ])
    if settings.web:
        for t in web_tools(client, settings):
            tools.add(t)

    actions = "\n".join(f"- {a.name}({', '.join(a.parameters.get('properties', {}))}): {a.doc()}"
                        for a in env.actions())
    prompt = DEVELOPER_PROMPT.format(
        env_name=env.name, env_brief=env.brief, actions=actions, max_steps=env.max_steps,
        train_tasks="\n".join(f"- {t.id}: {t.instruction}" for t in train),
        tiers=", ".join(MODEL_TIERS), genome=genome.describe(), evidence=evidence.render(),
        trials=max_trials)

    run = run_agent(client, settings.model_develop, prompt,
                    "Begin. Decide what this agent should become, and develop it.",
                    tools, max_steps=max_steps, temperature=0.4, max_tokens=2500, log=log,
                    extra=reasoning_extra(settings.model_develop, settings.reasoning_develop))
    summary = run.final or f"(development stopped: {run.stopped}; {run.error})"
    return DevResult(summary, run, trials)
