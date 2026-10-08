"""The agent loop: model + prompt + tools, step by step, until `finish`.

Guarantees live here, in code, not in prompts: the step limit, the budget,
the verification hook on `finish`, and context compaction.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from .llm import LLMError, StopRun
from .tools import Tool, ToolSet, clip, schema

FINISH = "finish"
KEEP_RECENT = 4              # newest tool results / tool calls kept verbatim
COMPACT_ABOVE_CHARS = 10_000 # free-tier models allow ~6-8K tokens per minute; stay well below


@dataclass
class Step:
    n: int
    tool: str
    args: dict
    result: str


@dataclass
class RunResult:
    final: str = ""
    stopped: str = "finished"   # finished | max_steps | error
    steps: list[Step] = field(default_factory=list)
    error: str = ""

    def digest(self, max_lines: int = 14, width: int = 160) -> str:
        """Short, human-readable account of what the agent did."""
        lines = []
        for s in self.steps[:max_lines]:
            args = json.dumps(s.args, ensure_ascii=False)
            lines.append(f"{s.n}. {s.tool}({clip(args, 90)}) -> {clip(s.result.replace(chr(10), ' '), width)}")
        if len(self.steps) > max_lines:
            lines.append(f"... {len(self.steps) - max_lines} more steps")
        lines.append(f"stopped: {self.stopped}; final answer: {clip(self.final, 200)}")
        if self.error:
            lines.append(f"error: {self.error}")
        return "\n".join(lines)


def _finish_tool() -> Tool:
    return Tool(FINISH, "Call this exactly once when you are done. `answer` is your final "
                        "answer or a short summary of what you did.",
                schema({"answer": {"type": "string"}}, ["answer"]), lambda a: "ok")


def _size(messages: list[dict]) -> int:
    total = 0
    for m in messages[2:]:  # system prompt and task are never compacted
        total += len(str(m.get("content") or ""))
        for tc in m.get("tool_calls") or []:
            total += len(tc["function"].get("arguments") or "")
    return total


def _compact(messages: list[dict], limit: int = COMPACT_ABOVE_CHARS) -> None:
    """Shrink old tool results and old tool-call arguments (e.g. code that was
    written several steps ago) once the conversation grows past `limit`.
    Keeps the newest items intact, fewer of them if that is still too much."""
    keep = KEEP_RECENT
    while _size(messages) > limit and keep >= 1:
        tool_idx = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
        for i in tool_idx[:-keep]:
            content = messages[i].get("content") or ""
            if len(content) > 300:
                messages[i]["content"] = content[:200] + f" ...[older result elided, {len(content)} chars]"
        call_idx = [i for i, m in enumerate(messages) if m.get("tool_calls")]
        for i in call_idx[:-keep]:
            for tc in messages[i]["tool_calls"]:
                args = tc["function"].get("arguments") or ""
                if len(args) > 400:
                    tc["function"]["arguments"] = json.dumps({"_elided": f"{len(args)} chars of arguments"})
        keep -= 1


def _assistant_record(msg: dict) -> dict:
    rec: dict[str, Any] = {"role": "assistant", "content": msg.get("content") or ""}
    if msg.get("tool_calls"):
        rec["tool_calls"] = [{"id": tc.get("id"), "type": "function",
                              "function": {"name": tc["function"]["name"],
                                           "arguments": tc["function"].get("arguments") or "{}"}}
                             for tc in msg["tool_calls"]]
    return rec


def run_agent(client: Any, model: str, system: str, user: str, tools: ToolSet,
              max_steps: int = 12, temperature: float = 0.2, max_tokens: int = 1024,
              on_finish: Callable[[str], str | None] | None = None,
              reflect_every: int = 0,
              log: Callable[[str], None] | None = None,
              extra: dict | None = None) -> RunResult:
    """Run one agent episode.

    on_finish(answer) may return a string to reject the answer; the loop then
    hands the rejection back to the model (at most twice) instead of stopping.
    """
    log = log or (lambda _m: None)
    if tools.get(FINISH) is None:
        tools.add(_finish_tool())
    messages: list[dict] = [{"role": "system", "content": system},
                            {"role": "user", "content": user}]
    result = RunResult()
    nudges = rejections = 0

    for n in range(1, max_steps + 1):
        _compact(messages)
        try:
            try:
                msg = client.chat(model, messages, tools.specs(), temperature=temperature,
                                  max_tokens=max_tokens, extra=extra)
            except LLMError as e:
                if isinstance(e, StopRun) or not any(k in str(e).lower() for k in ("413", "too large", "context")):
                    raise
                log("  request too large; compacting the conversation hard and retrying")
                _compact(messages, limit=2_000)
                msg = client.chat(model, messages, tools.specs(), temperature=temperature,
                                  max_tokens=max_tokens, extra=extra)
        except StopRun:
            raise  # quota or budget: the caller saves progress and stops the run
        except LLMError as e:
            result.stopped, result.error = "error", str(e)
            return result

        messages.append(_assistant_record(msg))
        calls = msg.get("tool_calls") or []
        if not calls:
            text = (msg.get("content") or "").strip()
            if nudges < 2:
                nudges += 1
                messages.append({"role": "user", "content":
                                 "Act through your tools. When you are done, call finish(answer)."})
                continue
            result.final, result.stopped = text, "finished"
            return result

        for tc in calls:
            name = tc["function"]["name"]
            raw = tc["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else dict(raw)
                if not isinstance(args, dict):
                    raise ValueError("arguments must be a JSON object")
            except (ValueError, TypeError) as e:
                out = f"ERROR: arguments for {name} were not valid JSON ({e}). Try again."
                messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": out})
                result.steps.append(Step(n, name, {"_raw": str(raw)[:200]}, out))
                continue

            if name == FINISH:
                answer = str(args.get("answer", ""))
                verdict = on_finish(answer) if on_finish else None
                if verdict and rejections < 2:
                    rejections += 1
                    out = f"Not accepted yet: {verdict}"
                    messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": out})
                    result.steps.append(Step(n, name, args, out))
                    continue
                result.steps.append(Step(n, name, args, "ok"))
                result.final, result.stopped = answer, "finished"
                return result

            out = tools.call(name, args)
            log(f"  step {n}: {name} -> {clip(out, 120)}")
            messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": out})
            result.steps.append(Step(n, name, args, out))

        if reflect_every and n % reflect_every == 0 and n < max_steps:
            messages.append({"role": "user", "content":
                             f"Step {n} of {max_steps}. Check your progress against the goal "
                             "and adjust your approach if it is not working."})

    result.stopped = "max_steps"
    return result
