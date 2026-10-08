"""Tool definitions shared by every agent loop."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from .llm import StopRun

MAX_RESULT_CHARS = 2500


def clip(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]} ...[+{len(text) - limit} chars]"


def to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def schema(properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties or {}, "required": required or []}


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable[[dict], Any]

    def spec(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description, "parameters": self.parameters}}


class ToolSet:
    def __init__(self, tools: list[Tool] | None = None, result_limit: int = MAX_RESULT_CHARS):
        self._tools: dict[str, Tool] = {}
        self.result_limit = result_limit
        for t in tools or []:
            self.add(t)

    def add(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return list(self._tools)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[dict]:
        return [t.spec() for t in self._tools.values()]

    def call(self, name: str, args: dict) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"ERROR: unknown tool '{name}'. Available: {', '.join(self._tools)}"
        try:
            return clip(to_text(tool.fn(args)), self.result_limit)
        except StopRun:
            raise
        except Exception as e:  # tool errors go back to the model, not up the stack
            return f"ERROR in {name}: {type(e).__name__}: {e}"
