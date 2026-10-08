"""What an environment provides to the agent.

An environment is a place, not a lesson: a short description of what exists
there, a set of raw actions, tasks, and a grader. It never tells the agent
how to succeed. Scores are computed from what the agent actually did and
answered, never from what it claims.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Task:
    id: str
    split: str            # "train" (visible during development) or "test" (held out)
    instruction: str
    params: dict = field(default_factory=dict)


@dataclass
class Action:
    name: str
    description: str
    parameters: dict
    fn: Callable[..., Any]


class Environment(ABC):
    name: str = ""
    brief: str = ""              # what this place is; no strategy hints
    max_steps: int = 14          # agent turns per task (upper bound for any genome)
    max_internal_calls: int = 6000

    def __init__(self) -> None:
        self.task: Task | None = None
        self.calls = 0

    # -- tasks --------------------------------------------------------------
    @abstractmethod
    def tasks(self, split: str) -> list[Task]: ...

    def task_by_id(self, task_id: str) -> Task:
        for split in ("train", "test"):
            for t in self.tasks(split):
                if t.id == task_id:
                    return t
        raise KeyError(task_id)

    def start(self, task: Task) -> None:
        self.task = task
        self.calls = 0
        self._start(task)

    @abstractmethod
    def _start(self, task: Task) -> None: ...

    # -- acting -------------------------------------------------------------
    @abstractmethod
    def actions(self) -> list[Action]: ...

    def call(self, name: str, args: dict) -> Any:
        if self.task is None:
            raise RuntimeError("environment not started")
        self.calls += 1
        if self.calls > self.max_internal_calls:
            raise RuntimeError(f"too many environment calls in this task (limit {self.max_internal_calls})")
        for a in self.actions():
            if a.name == name:
                return a.fn(**(args or {}))
        raise ValueError(f"unknown action '{name}'")

    # -- grading ------------------------------------------------------------
    @abstractmethod
    def score(self, answer: str) -> tuple[float, str]:
        """Return (score in [0, 1], short note on how it was computed)."""
