"""OpenAI-compatible chat client with tool calling, rate-limit pacing and a
hard token budget.

Built for free-tier quotas: it waits on HTTP 429 using `retry-after`, paces
itself with the `x-ratelimit-*` headers, and raises `QuotaExhausted` when a
daily limit is hit so the caller can stop cleanly and resume later.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import requests


class LLMError(RuntimeError):
    pass


class StopRun(LLMError):
    """Stop the whole run (not just one episode); progress on disk is kept."""


class BudgetExceeded(StopRun):
    """The per-process token budget is spent."""


class QuotaExhausted(StopRun):
    """The provider's daily quota is spent. Resume after it resets."""


class ConfigError(StopRun):
    """Wrong key, retired or inaccessible model: nothing will work until it is fixed."""


def reasoning_extra(model: str, effort: str | None) -> dict:
    """gpt-oss models spend tokens on reasoning; let callers choose how much."""
    if effort and "gpt-oss" in model:
        return {"reasoning_effort": effort}
    return {}


_THINK = re.compile(r"<think>.*?</think>", re.S)


def _parse_duration(value: str | None) -> float:
    """Parse Groq reset headers such as '7.66s', '1m2.5s', '350ms'."""
    if not value:
        return 0.0
    total = 0.0
    for num, unit in re.findall(r"([\d.]+)(ms|h|m|s)", value):
        n = float(num)
        total += {"ms": n / 1000, "s": n, "m": n * 60, "h": n * 3600}[unit]
    if total == 0.0:
        try:
            total = float(value)
        except ValueError:
            pass
    return total


@dataclass
class Usage:
    calls: int = 0
    prompt: int = 0
    completion: int = 0
    by_model: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return self.prompt + self.completion

    def add(self, model: str, prompt: int, completion: int) -> None:
        self.calls += 1
        self.prompt += prompt
        self.completion += completion
        self.by_model[model] = self.by_model.get(model, 0) + prompt + completion


class ChatClient:
    def __init__(self, api_base: str, api_key: str, token_budget: int = 400_000,
                 timeout: int = 120, log: Callable[[str], None] | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 fallbacks: dict[str, str] | None = None):
        if not api_key:
            raise LLMError("No API key. Put GROQ_API_KEY=... in .env (see .env.example).")
        self.url = api_base.rstrip("/") + "/chat/completions"
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self.budget = token_budget
        self.timeout = timeout
        self.usage = Usage()
        self.log = log or (lambda _m: None)
        self.sleep = sleep
        # model -> (remaining tokens, seconds to full reset, per-minute limit, timestamp)
        self._limits: dict[str, tuple[int, float, int, float]] = {}
        self.fallbacks = dict(fallbacks or {})   # model -> model to use once its daily quota is gone
        self.exhausted: set[str] = set()

    # -- pacing ---------------------------------------------------------
    def _pace(self, model: str, est_tokens: int) -> None:
        """Wait only as long as the token bucket needs to refill for this request."""
        info = self._limits.get(model)
        if not info:
            return
        remaining, reset_s, limit, stamp = info
        elapsed = time.monotonic() - stamp
        rate = (limit / 60.0) if limit else 0.0          # tokens refilled per second
        available = remaining + rate * elapsed if rate else remaining
        if available >= est_tokens or elapsed >= reset_s:
            return
        need = est_tokens - available
        pause = min(need / rate if rate else reset_s - elapsed, reset_s - elapsed, 65.0) + 0.5
        self.log(f"[pace] {model}: waiting {pause:.0f}s for the per-minute token limit")
        self.sleep(pause)

    def _remember_limits(self, model: str, headers: Any) -> None:
        try:
            remaining = int(headers.get("x-ratelimit-remaining-tokens", ""))
        except (TypeError, ValueError):
            return
        try:
            limit = int(headers.get("x-ratelimit-limit-tokens", "0"))
        except (TypeError, ValueError):
            limit = 0
        reset = _parse_duration(headers.get("x-ratelimit-reset-tokens"))
        self._limits[model] = (remaining, reset, limit, time.monotonic())

    # -- main call --------------------------------------------------------
    def chat(self, model: str, messages: list[dict], tools: list[dict] | None = None,
             temperature: float = 0.2, max_tokens: int = 1024,
             extra: dict | None = None) -> dict:
        while model in self.exhausted and self.fallbacks.get(model):
            model = self.fallbacks[model]
        try:
            return self._chat(model, messages, tools, temperature, max_tokens, extra)
        except QuotaExhausted:
            alt = self.fallbacks.get(model)
            if not alt or alt in self.exhausted:
                raise
            self.exhausted.add(model)
            self.log(f"[quota] {model} is out of daily tokens; continuing with {alt}")
            extra = {k: v for k, v in (extra or {}).items() if k != "reasoning_effort"} or None
            return self.chat(alt, messages, tools, temperature, max_tokens, extra)

    def _chat(self, model: str, messages: list[dict], tools: list[dict] | None,
              temperature: float, max_tokens: int, extra: dict | None) -> dict:
        if self.usage.total >= self.budget:
            raise BudgetExceeded(f"token budget {self.budget} spent ({self.usage.total} used)")

        body: dict[str, Any] = {"model": model, "messages": messages,
                                "temperature": temperature, "max_tokens": max_tokens}
        if tools:
            body["tools"] = tools
        if extra:
            body.update(extra)

        # Typical replies are far shorter than max_tokens; a 429 is handled anyway.
        est = (len(json.dumps(messages)) + len(json.dumps(tools or []))) // 4 + min(max_tokens, 800)
        nudged = False
        for attempt in range(8):
            self._pace(model, est)
            try:
                r = requests.post(self.url, headers=self.headers, json=body, timeout=self.timeout)
            except requests.RequestException as e:
                if attempt >= 3:
                    raise LLMError(f"network error: {e}") from e
                self.sleep(2 ** attempt)
                continue

            self._remember_limits(model, r.headers)

            if r.status_code == 200:
                data = r.json()
                u = data.get("usage") or {}
                self.usage.add(model, int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0)))
                msg = data["choices"][0]["message"]
                if isinstance(msg.get("content"), str):
                    msg["content"] = _THINK.sub("", msg["content"]).strip()
                return msg

            text = r.text[:600]
            if r.status_code == 429:
                low = text.lower()
                if "per day" in low or "(rpd)" in low or "(tpd)" in low or "daily" in low:
                    raise QuotaExhausted(f"{model}: daily limit reached. {text[:200]}")
                wait = _parse_duration(r.headers.get("retry-after")) or min(2 ** attempt * 2, 60)
                self.log(f"[429] {model}: waiting {wait:.0f}s")
                self.sleep(min(wait + 0.5, 65.0))
                continue
            if r.status_code == 400 and "tool_use_failed" in text and not nudged:
                # The model produced a malformed tool call. Ask once more, explicitly.
                nudged = True
                body["messages"] = messages + [{
                    "role": "user",
                    "content": "Your last tool call was malformed. Call a tool with valid JSON "
                               "arguments that match its schema, or call finish."}]
                continue
            if r.status_code == 400 and "tool_use_failed" in text:
                failed = ""
                try:
                    failed = r.json()["error"].get("failed_generation", "")
                except Exception:
                    pass
                self.log(f"[tool_use_failed] {model}: giving the model's text back to the loop")
                return {"role": "assistant", "content": failed or "(malformed tool call)"}
            if r.status_code in (401, 403, 404):
                raise ConfigError(f"{model}: HTTP {r.status_code}: {text[:300]}")
            if r.status_code in (500, 502, 503, 504):
                self.sleep(min(2 ** attempt * 2, 30))
                continue
            raise LLMError(f"{model}: HTTP {r.status_code}: {text}")
        raise LLMError(f"{model}: gave up after repeated rate limiting / server errors")


class ScriptedClient:
    """Test double. `script` is a list of assistant messages (or callables
    taking (model, messages, tools) and returning one)."""

    def __init__(self, script: list[Any]):
        self.script = list(script)
        self.usage = Usage()
        self.calls: list[dict] = []

    def chat(self, model: str, messages: list[dict], tools: list[dict] | None = None,
             **_: Any) -> dict:
        self.calls.append({"model": model, "messages": [dict(m) for m in messages], "tools": tools})
        if not self.script:
            return {"role": "assistant", "content": "", "tool_calls": [
                {"id": "auto", "type": "function",
                 "function": {"name": "finish", "arguments": json.dumps({"answer": ""})}}]}
        item = self.script.pop(0)
        msg = item(model, messages, tools) if callable(item) else item
        self.usage.add(model, 100, 20)
        return msg


def tool_call(_tool: str, _id: str | None = None, **args: Any) -> dict:
    """Build an assistant message that calls one tool. Handy in tests."""
    return {"role": "assistant", "content": "", "tool_calls": [{
        "id": _id or f"call_{_tool}", "type": "function",
        "function": {"name": _tool, "arguments": json.dumps(args)}}]}
