"""Environments the stem agent can be pointed at.

These are the only modules allowed to know anything about a domain.
"""
from .archive import Archive
from .base import Action, Environment, Task
from .codeaudit import CodeAudit
from .exchange import Exchange

REGISTRY = {cls.name: cls for cls in (Exchange, CodeAudit, Archive)}


def make(name: str) -> Environment:
    try:
        return REGISTRY[name]()
    except KeyError:
        raise SystemExit(f"unknown environment '{name}'. Available: {', '.join(REGISTRY)}")


__all__ = ["Action", "Environment", "Task", "REGISTRY", "make"]
