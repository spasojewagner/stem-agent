from stem.llm import ScriptedClient, StopRun, BudgetExceeded, tool_call
from stem.loop import run_agent
from stem.tools import Tool, ToolSet, schema
import pytest


def counter():
    state = {"n": 0}
    t = Tool("inc", "increment", schema({}), lambda a: state.__setitem__("n", state["n"] + 1) or state["n"])
    return state, ToolSet([t])


def test_runs_tools_until_finish():
    state, tools = counter()
    client = ScriptedClient([tool_call("inc"), tool_call("inc"), tool_call("finish", answer="two")])
    res = run_agent(client, "m", "sys", "go", tools, max_steps=5)
    assert res.final == "two" and res.stopped == "finished" and state["n"] == 2


def test_step_limit_is_enforced_in_code():
    state, tools = counter()
    client = ScriptedClient([tool_call("inc")] * 10)
    res = run_agent(client, "m", "sys", "go", tools, max_steps=3)
    assert res.stopped == "max_steps" and state["n"] == 3


def test_bad_arguments_are_reported_back():
    _, tools = counter()
    bad = {"role": "assistant", "content": "", "tool_calls": [
        {"id": "x", "type": "function", "function": {"name": "inc", "arguments": "{not json"}}]}
    client = ScriptedClient([bad, tool_call("finish", answer="ok")])
    res = run_agent(client, "m", "sys", "go", tools, max_steps=4)
    assert res.final == "ok" and "not valid JSON" in res.steps[0].result


def test_finish_hook_can_reject():
    _, tools = counter()
    client = ScriptedClient([tool_call("finish", answer="draft"), tool_call("finish", answer="final")])
    seen = []
    res = run_agent(client, "m", "sys", "go", tools, max_steps=4,
                    on_finish=lambda a: (seen.append(a), None if a == "final" else "check again")[1])
    assert res.final == "final" and seen == ["draft", "final"]


def test_text_without_tools_is_nudged_then_accepted():
    _, tools = counter()
    text = {"role": "assistant", "content": "I think the answer is 7"}
    res = run_agent(ScriptedClient([text, text, text]), "m", "sys", "go", tools, max_steps=5)
    assert res.final == "I think the answer is 7" and res.stopped == "finished"


def test_stop_run_propagates():
    _, tools = counter()

    def boom(*_):
        raise BudgetExceeded("spent")
    with pytest.raises(StopRun):
        run_agent(ScriptedClient([boom]), "m", "sys", "go", tools)


def test_old_code_and_results_are_compacted():
    from stem.loop import _compact, _size
    big = "x" * 3000
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    for i in range(8):
        msgs.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": str(i), "type": "function", "function": {"name": "write", "arguments": '{"code": "' + big + '"}'}}]})
        msgs.append({"role": "tool", "tool_call_id": str(i), "content": big})
    before = _size(msgs)
    _compact(msgs)
    assert _size(msgs) < before / 2
    assert msgs[-1]["content"] == big and big in msgs[-2]["tool_calls"][0]["function"]["arguments"]
    import json
    for m in msgs:
        for tc in m.get("tool_calls") or []:
            json.loads(tc["function"]["arguments"])  # still valid JSON


def test_request_too_large_compacts_and_retries():
    from stem.llm import LLMError
    _, tools = counter()

    def too_large(*_):
        raise LLMError("m: HTTP 413: Request too large for model")
    res = run_agent(ScriptedClient([too_large, tool_call("finish", answer="ok")]), "m", "s", "u", tools)
    assert res.final == "ok"
