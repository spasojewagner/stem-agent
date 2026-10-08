"""Settings, read from environment variables or a local `.env` file.

Defaults target Groq's OpenAI-compatible API, but any endpoint that speaks
the OpenAI chat-completions protocol with tool calling works (OpenAI,
OpenRouter, a local Ollama at http://localhost:11434/v1, ...).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def load_dotenv(path: str | os.PathLike = ".env") -> None:
    """Minimal .env loader. Existing environment variables win."""
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    api_base: str = "https://api.groq.com/openai/v1"
    api_key: str = ""
    # Three model tiers. On Groq's free plan every model has its own daily
    # token bucket, so spreading the work across models stretches the quota.
    model_develop: str = "openai/gpt-oss-120b"    # the developmental process
    model_act: str = "openai/gpt-oss-20b"         # the agent doing tasks
    model_fast: str = "qwen/qwen3.8-27b"          # sub-agents, cheap calls
    model_search: str = "openai/gpt-oss-20b"      # server-side web search
    reasoning_develop: str = "medium"             # gpt-oss reasoning effort per role
    reasoning_act: str = "low"
    token_budget: int = 400_000                   # hard stop per process
    web: bool = True                              # web tools for development
    web_allow: list[str] = field(default_factory=list)
    tool_timeout: int = 30                        # seconds per tool call
    runs_dir: Path = Path("runs")

    @classmethod
    def from_env(cls, dotenv: str | None = ".env") -> "Settings":
        if dotenv:
            load_dotenv(dotenv)
        allow = os.environ.get("STEM_WEB_ALLOW", "en.wikipedia.org,docs.python.org")
        return cls(
            api_base=os.environ.get("STEM_API_BASE", cls.api_base).rstrip("/"),
            api_key=os.environ.get("STEM_API_KEY") or os.environ.get("GROQ_API_KEY", ""),
            model_develop=os.environ.get("STEM_MODEL_DEVELOP", cls.model_develop),
            model_act=os.environ.get("STEM_MODEL_ACT", cls.model_act),
            model_fast=os.environ.get("STEM_MODEL_FAST", cls.model_fast),
            model_search=os.environ.get("STEM_MODEL_SEARCH", cls.model_search),
            reasoning_develop=os.environ.get("STEM_REASONING_DEVELOP", cls.reasoning_develop),
            reasoning_act=os.environ.get("STEM_REASONING_ACT", cls.reasoning_act),
            token_budget=_int("STEM_TOKEN_BUDGET", cls.token_budget),
            web=_bool("STEM_WEB", cls.web),
            web_allow=[d.strip().lower() for d in allow.split(",") if d.strip()],
            tool_timeout=_int("STEM_TOOL_TIMEOUT", cls.tool_timeout),
            runs_dir=Path(os.environ.get("STEM_RUNS_DIR", "runs")),
        )

    def model_for(self, tier: str) -> str:
        return {"develop": self.model_develop, "act": self.model_act,
                "fast": self.model_fast}.get(tier, self.model_act)
