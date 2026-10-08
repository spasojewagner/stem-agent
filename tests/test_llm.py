import pytest

from stem import llm
from stem.llm import BudgetExceeded, ChatClient, QuotaExhausted, _parse_duration


class Resp:
    def __init__(self, status, body=None, headers=None, text=""):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = text or (str(body) if body else "")

    def json(self):
        return self._body


OK = Resp(200, {"choices": [{"message": {"role": "assistant", "content": "<think>x</think>hi"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5}},
          {"x-ratelimit-remaining-tokens": "7000", "x-ratelimit-reset-tokens": "7.5s"})


def client(monkeypatch, responses, budget=10_000):
    calls, sleeps = [], []

    def post(url, headers, json, timeout):
        calls.append(json)
        return responses.pop(0)
    monkeypatch.setattr(llm.requests, "post", post)
    return ChatClient("https://x/v1", "k", budget, sleep=sleeps.append), calls, sleeps


def test_parse_duration():
    assert _parse_duration("7.66s") == pytest.approx(7.66)
    assert _parse_duration("1m2.5s") == pytest.approx(62.5)
    assert _parse_duration("350ms") == pytest.approx(0.35)
    assert _parse_duration("12") == 12


def test_waits_on_429_then_succeeds(monkeypatch):
    c, calls, sleeps = client(monkeypatch, [Resp(429, headers={"retry-after": "3"}, text="rate limit TPM"), OK])
    msg = c.chat("m", [{"role": "user", "content": "hi"}])
    assert msg["content"] == "hi" and len(calls) == 2 and sleeps and sleeps[0] >= 3
    assert c.usage.total == 15 and c.usage.by_model == {"m": 15}


def test_daily_limit_stops_the_run(monkeypatch):
    c, _, _ = client(monkeypatch, [Resp(429, text="Rate limit reached ... tokens per day (TPD): Limit 200000")])
    with pytest.raises(QuotaExhausted):
        c.chat("m", [{"role": "user", "content": "hi"}])


def test_malformed_tool_call_is_retried_once(monkeypatch):
    bad = Resp(400, {"error": {"code": "tool_use_failed", "failed_generation": "oops"}},
               text='{"error":{"code":"tool_use_failed"}}')
    c, calls, _ = client(monkeypatch, [bad, OK])
    assert c.chat("m", [{"role": "user", "content": "hi"}])["content"] == "hi"
    assert "malformed" in calls[1]["messages"][-1]["content"]


def test_budget(monkeypatch):
    c, _, _ = client(monkeypatch, [OK, OK], budget=10)
    c.chat("m", [{"role": "user", "content": "hi"}])
    with pytest.raises(BudgetExceeded):
        c.chat("m", [{"role": "user", "content": "hi"}])


def test_paces_itself_when_window_is_nearly_spent(monkeypatch):  # no limit header: waits for reset
    low = Resp(200, OK._body, {"x-ratelimit-remaining-tokens": "50", "x-ratelimit-reset-tokens": "20s"})
    c, _, sleeps = client(monkeypatch, [low, OK])
    c.chat("m", [{"role": "user", "content": "hi"}])
    c.chat("m", [{"role": "user", "content": "hi"}], max_tokens=1000)
    assert sleeps and 15 < sleeps[0] <= 21


def test_retired_model_stops_the_run(monkeypatch):
    from stem.llm import ConfigError, StopRun
    gone = Resp(404, text='{"error":{"message":"The model `llama-3.3-70b-versatile` does not exist","code":"model_not_found"}}')
    c, _, _ = client(monkeypatch, [gone])
    with pytest.raises(ConfigError) as info:
        c.chat("llama-3.3-70b-versatile", [{"role": "user", "content": "hi"}])
    assert isinstance(info.value, StopRun) and "404" in str(info.value)


def test_pacing_waits_only_for_the_refill(monkeypatch):
    # 8000 tokens/min -> 133 tokens/s; 200 left and ~650 needed -> a few seconds, not the full reset
    low = Resp(200, OK._body, {"x-ratelimit-remaining-tokens": "200", "x-ratelimit-limit-tokens": "8000",
                               "x-ratelimit-reset-tokens": "58s"})
    c, _, sleeps = client(monkeypatch, [low, OK])
    c.chat("m", [{"role": "user", "content": "hi"}])
    c.chat("m", [{"role": "user", "content": "hi"}], max_tokens=600)
    assert sleeps and sleeps[0] < 10


def test_reasoning_effort_only_for_gpt_oss():
    from stem.llm import reasoning_extra
    assert reasoning_extra("openai/gpt-oss-20b", "low") == {"reasoning_effort": "low"}
    assert reasoning_extra("qwen/qwen3.8-27b", "low") == {}


def test_development_falls_back_when_quota_is_gone(monkeypatch):
    calls, sleeps = [], []
    gone = Resp(429, text="Rate limit reached on tokens per day (TPD): Limit 200000")
    responses = [gone, OK, OK]

    def post(url, headers, json, timeout):
        calls.append(json["model"])
        return responses.pop(0)
    monkeypatch.setattr(llm.requests, "post", post)
    c = ChatClient("https://x/v1", "k", 10_000, sleep=sleeps.append, fallbacks={"big": "other"})
    c.chat("big", [{"role": "user", "content": "hi"}], extra={"reasoning_effort": "low"})
    c.chat("big", [{"role": "user", "content": "hi"}])
    assert calls == ["big", "other", "other"]
