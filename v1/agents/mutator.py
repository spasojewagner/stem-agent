"""
Mutator -- sees which tests failed, proposes ONE mutation that might address them.

A mutation is either:
  (a) a new natural-language strategy to add to the genome
  (b) a tool to enable from the registry  (only when tools_mode is on)
  (c) a tool to disable                    (only when tools_mode is on)

Tracks discarded mutations to avoid suggesting the same thing twice.
"""
import os
import json
import requests

from agents.tools import describe_tools, available_tools

# Track what was tried and discarded this session
_discarded_strategies = []
_discarded_tools      = []   # tools we tried to enable that didn't help


def record_discarded(strategy: str = None, tool: str = None):
    if strategy and strategy not in _discarded_strategies:
        _discarded_strategies.append(strategy)
    if tool and tool not in _discarded_tools:
        _discarded_tools.append(tool)


def suggest_mutation(genome: dict,
                     score: float,
                     failures_by_type: dict,
                     task_results: list = None,
                     tools_mode: bool = False) -> dict:
    """
    Returns a dict that the evolution loop will pass to apply_mutation().
    Always has at most one of {strategy, add_tool, remove_tool} set.

    Examples of return values:
      {"strategy": "Add clear() method...", "reason": "...", "remove": null,
       "add_tool": null, "remove_tool": null}
      {"strategy": null, "reason": "...", "add_tool": "PublicAPIExpander",
       "remove_tool": null, "remove": null}
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    model   = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    current_strategies = genome.get("strategies", [])
    current_tools      = genome.get("tools", [])

    failing_tests = []
    if task_results:
        for t in task_results:
            output = t.get("test_output", "")
            for line in output.split("\n"):
                if "[FAIL]" in line:
                    failing_tests.append(line.strip())

    tool_section = ""
    if tools_mode:
        tool_descriptions = describe_tools()
        available          = [t for t in available_tools() if t not in current_tools]
        tool_section = f"""
You may ALSO propose a TOOL mutation instead of a strategy. Tools wrap the
solver's call -- pre-solve tools add context to the prompt, post-solve tools
revise the code after it's written.

Currently enabled tools:  {current_tools if current_tools else "(none)"}
Available tools to enable:
""" + "\n".join(f"  - {t}: {tool_descriptions[t]}" for t in available) + f"""

Previously discarded tools (do NOT re-enable):  {_discarded_tools if _discarded_tools else "(none)"}

When choosing a tool: pick based on what the FAILURES suggest. For example,
'is not a function' on add/remove/size hints at PublicAPIExpander.
'should handle empty' across many tests hints at EdgeCasePredictor.
Generic structural failures hint at SpecAnalyzer.
Subtle bugs hint at SelfCritique.
"""

    remove_section = ""
    if current_strategies:
        remove_section = """
You may also REMOVE a strategy if it seems counterproductive or redundant.
Set "remove" to the exact text of the strategy to remove, or null to keep all.
"""

    discarded_section = ""
    if _discarded_strategies:
        discarded_section = f"""
Previously tried strategies that FAILED (do NOT suggest these again):
{json.dumps(_discarded_strategies, indent=2)}
"""

    prompt = f"""You are evolving a system prompt for an AI JavaScript engineer.

The agent receives a vague specification and must implement a JavaScript class from scratch.
It does NOT see the tests -- it must predict what a correct implementation needs.

Current strategies ({len(current_strategies)} total):
{json.dumps(current_strategies, indent=2) if current_strategies else "  (none -- raw LLM)"}

Current score: {score:.1%}
{discarded_section}
Tests currently FAILING:
{chr(10).join(failing_tests) if failing_tests else "  (none or no data)"}
{remove_section}{tool_section}
Propose ONE mutation. It can be either:
  - a NEW strategy (a concrete thinking instruction)
  - {"OR an add_tool / remove_tool mutation" if tools_mode else "(strategy only -- tools mode is off)"}

Good strategy examples (only when you propose a strategy):
  "Implement once(event, fn): wrap fn in a one-time wrapper that calls off() after first fire"
  "Wrap each listener call in try/catch so one throwing listener does not block subsequent ones"
  "Make emit() copy the listener array before iterating"
  "LRUCache: use a Map + doubly-linked list; get() and set() both move to head"
  "PromisePool.run(): start up to concurrency tasks; resolve in original index order"

Respond ONLY with JSON (no markdown):
{{
  "strategy":     "exact instruction text, or null if proposing a tool",
  "add_tool":     "ToolName, or null",
  "remove_tool":  "ToolName, or null",
  "remove":       null,
  "reason":       "which failing tests this addresses"
}}"""

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "max_tokens": 400,
                "temperature": 0.8,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )

        if response.status_code != 200:
            raise Exception(f"API error {response.status_code}")

        content = response.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        result = json.loads(content.strip())

        # Normalize: make sure every key exists with sensible default
        result.setdefault("strategy",    None)
        result.setdefault("add_tool",    None)
        result.setdefault("remove_tool", None)
        result.setdefault("remove",      None)
        result.setdefault("reason",      "")

        # Validate remove
        if result.get("remove") and result["remove"] not in current_strategies:
            result["remove"] = None

        # Validate tool fields
        if result.get("add_tool") and result["add_tool"] not in available_tools():
            result["add_tool"] = None
        if result.get("remove_tool") and result["remove_tool"] not in current_tools:
            result["remove_tool"] = None

        return result

    except Exception as e:
        return {
            "strategy": "List every public method the class needs before writing any code, then implement each one completely",
            "reason": f"Fallback: {e}",
            "remove": None,
            "add_tool": None,
            "remove_tool": None,
        }
