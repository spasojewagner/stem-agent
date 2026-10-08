"""
Tool registry -- optional components the agent can enable or disable
through evolution.

Each Tool is a small component with a clear role and a single `run(context)`
method. Tools belong to one of two phases:

  pre_solve   -- run BEFORE the solver writes code. Output is appended to
                 the solver's system prompt as extra context (analysis,
                 edge-case list, etc).

  post_solve  -- run AFTER the solver writes code. May rewrite the code,
                 add method aliases, surface critique notes.

The mutator can propose `+tool: X` or `-tool: X` mutations alongside the
existing natural-language strategy mutations. The genome stores which tools
are enabled. Default genome has zero tools.

If --use-tools is NOT set on the CLI, the tool pipeline is bypassed entirely.
"""

import os
import re
import requests


# Tool base class

class Tool:
    name: str         = ""   # short identifier used in the genome
    description: str  = ""   # one-line description shown to the mutator
    phase: str        = ""   # "pre_solve" or "post_solve"

    def run(self, context: dict) -> dict:
        """
        context contains at minimum:
          - "spec": the task spec the solver will see
          - "code": the solver's output (only in post_solve)
          - "failures": failing test names (only in post_solve)
          - "previous_outputs": dict of outputs from earlier tools

        Returns a dict that gets merged into context for the next tool /
        for the solver's augmented prompt.
        """
        raise NotImplementedError


# Helper: shared LLM call for tools that need one

def _call_llm(prompt: str, max_tokens: int = 600, temperature: float = 0.2) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    model   = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=30
    )
    if response.status_code != 200:
        raise Exception(f"Tool LLM error {response.status_code}: {response.text[:160]}")
    return response.json()["choices"][0]["message"]["content"].strip()


# Concrete tools

class SpecAnalyzer(Tool):
    """Reads the spec and writes a structured analysis: likely methods,
    expected edge cases, and the data structure the implementation should use.
    Output is prepended to the solver's user message.
    """
    name        = "SpecAnalyzer"
    description = "Pre-solve LLM that lists likely methods + edge cases from the spec."
    phase       = "pre_solve"

    def run(self, context):
        spec = context["spec"]
        analysis = _call_llm(
            f"""Read this specification carefully and produce a short analysis.

Specification:
{spec}

Output a tight list:
1. Likely public methods (3-7 names)
2. Edge cases the implementation must handle (4-8 items)
3. Suggested data structure (1 sentence)

Be concrete and brief. Do NOT write code."""
        )
        return {"spec_analysis": analysis}


class EdgeCasePredictor(Tool):
    """Lists 6-10 concrete edge cases the implementation must handle.
    Output is appended to the solver's user message.
    """
    name        = "EdgeCasePredictor"
    description = "Pre-solve LLM that lists concrete edge cases to handle."
    phase       = "pre_solve"

    def run(self, context):
        spec = context["spec"]
        cases = _call_llm(
            f"""For this specification, list 6-10 concrete edge cases that
a careful implementation must handle. Each one line, no explanation.

Specification:
{spec}

Examples of what to list (do not copy these unless they apply):
- Empty input handling
- Duplicate operations
- Operation on missing key
- Negative or zero arguments
- Order preservation under mutation
- State leak between instances
- Off-by-one in size / capacity
- Return value when nothing to return (undefined vs null)

Output ONLY the list, one per line, hyphen-prefixed."""
        )
        return {"edge_cases": cases}


class SelfCritique(Tool):
    """Post-solve: reads the solver's code and proposes a revised version
    addressing the same spec, with attention to common omissions.
    Replaces `code` in context if it produces a better version.
    """
    name        = "SelfCritique"
    description = "Post-solve LLM that critiques and revises the solver's code."
    phase       = "post_solve"

    def run(self, context):
        spec = context["spec"]
        code = context.get("code", "")
        if not code:
            return {}

        revised = _call_llm(
            f"""You are reviewing a JavaScript class implementation. Spot weaknesses:
missing methods, missing edge cases, fragile error handling, returning the wrong
nullish value (null vs undefined), state leaks between instances.

Specification the implementation must satisfy:
{spec}

Current implementation:
```javascript
{code}
```

If the implementation has clear gaps, return a REVISED version that fixes them.
If the implementation is solid, return it unchanged.

Output ONLY a JavaScript code block, nothing else. Do not explain.""",
            max_tokens=1500, temperature=0
        )

        # Extract code from the response
        m = re.search(r"```(?:javascript|js)?\n(.*?)```", revised, re.DOTALL)
        revised_code = m.group(1).strip() if m else revised.strip()

        # Only replace if it parsed as code-block-ish output
        if revised_code and len(revised_code) >= 20 and "class" in revised_code:
            return {"code": revised_code, "critique_applied": True}
        return {}


class PublicAPIExpander(Tool):
    """Post-solve, NO LLM. After the solver writes its class, this tool
    looks at the method names and adds aliases that make the class easier
    for generic test introspection to find:

      - if class has `set(...)`, also expose `add(k, v)` that calls `set(k, v)`
      - if class has `delete(...)`, also expose `remove(k)`
      - if class has `has(...)`, also expose `contains(k)`
      - if class has nothing matching /size|length|count/, expose `size()`
        based on the detected internal storage (Map, Set, Array, or object).

    Intended for cases where the evaluator uses generic test introspection
    (add/remove/get/clear/size regex) but the agent picked domain-specific
    verbs (set/delete/has). Enabling this tool exposes both vocabularies.
    """
    name        = "PublicAPIExpander"
    description = "Post-solve (no LLM): adds add/remove/clear/size aliases for generic introspection."
    phase       = "post_solve"

    def run(self, context):
        code = context.get("code", "")
        if not code or "class " not in code:
            return {}

        # Find the class body (best-effort, single class assumed)
        class_match = re.search(r"class\s+(\w+)\s*\{(.+)\}\s*module\.exports", code, re.DOTALL)
        if not class_match:
            class_match = re.search(r"class\s+(\w+)\s*\{(.+)\}", code, re.DOTALL)
        if not class_match:
            return {}

        class_name = class_match.group(1)
        body       = class_match.group(2)

        # Detect existing methods
        method_names = set(re.findall(r"(?:^|\n)\s*([a-zA-Z_$][\w$]*)\s*\(", body))
        method_names.discard("constructor")
        method_names.discard("if")
        method_names.discard("for")
        method_names.discard("while")

        aliases = []

        def has_pattern(pat):
            return any(re.search(pat, m, re.IGNORECASE) for m in method_names)

        # Add aliases only if the canonical isn't there but the alias source is
        if "set" in method_names and not has_pattern(r"^(add|push|insert|put|enqueue)$"):
            aliases.append("    add(...args) { return this.set(...args); }")
        if "delete" in method_names and not has_pattern(r"^(remove|del|dequeue|pop)$"):
            aliases.append("    remove(...args) { return this.delete(...args); }")
        if "has" in method_names and not has_pattern(r"contains|exists"):
            aliases.append("    contains(...args) { return this.has(...args); }")
        if not has_pattern(r"^(size|length|count|total)$"):
            # Look for a candidate property: this.<name> = new Map() / new Set() / {} / []
            store_match = re.search(
                r"this\.(\w+)\s*=\s*(new\s+(?:Map|Set)\(\)|\{\}|\[\])", body
            )
            if store_match:
                prop = store_match.group(1)
                init = store_match.group(2)
                if "Map" in init or "Set" in init:
                    aliases.append(f"    size() {{ return this.{prop}.size; }}")
                elif "[" in init:
                    aliases.append(f"    size() {{ return this.{prop}.length; }}")
                else:
                    aliases.append(f"    size() {{ return Object.keys(this.{prop}).length; }}")

        if not aliases:
            return {}

        # Inject aliases just before the closing brace of the class body
        new_body = body.rstrip().rstrip("}")
        injected = new_body + "\n" + "\n".join(aliases) + "\n}"

        # Reassemble: replace the original class body
        new_code = code.replace(class_match.group(0),
                                code[class_match.start():class_match.end()]
                                    .replace(body, injected[:-len("}")] if False else
                                             "\n" + "\n".join(aliases) + "\n"))

        # Simpler: just inject before the final "}" of the class
        # Find the closing brace of the class
        idx = code.find("class ")
        if idx < 0:
            return {}
        # Find matching closing brace
        depth = 0
        start_brace = code.find("{", idx)
        if start_brace < 0:
            return {}
        i = start_brace
        while i < len(code):
            if code[i] == "{":
                depth += 1
            elif code[i] == "}":
                depth -= 1
                if depth == 0:
                    # i is the closing brace of the class
                    new_code = code[:i] + "\n" + "\n".join(aliases) + "\n" + code[i:]
                    return {"code": new_code, "aliases_added": [a.strip() for a in aliases]}
            i += 1

        return {}


# Registry -- the public API of this module

_REGISTRY = {
    SpecAnalyzer.name:         SpecAnalyzer,
    EdgeCasePredictor.name:    EdgeCasePredictor,
    SelfCritique.name:         SelfCritique,
    PublicAPIExpander.name:    PublicAPIExpander,
}


def available_tools() -> list:
    """List of all tool names that exist in the registry."""
    return list(_REGISTRY.keys())


def describe_tools() -> dict:
    """name -> description, for the mutator's prompt."""
    return {name: cls.description for name, cls in _REGISTRY.items()}


def get_tool(name: str):
    """Return a Tool instance for the given name, or None if unknown."""
    cls = _REGISTRY.get(name)
    return cls() if cls else None


def run_pre_solve_tools(enabled_tools: list, context: dict) -> dict:
    """
    Run all enabled pre_solve tools in registry order.
    Returns context augmentation (does NOT mutate input).
    Safe: each tool is wrapped in try/except.
    """
    out = {"previous_outputs": {}}
    for name in enabled_tools:
        tool = get_tool(name)
        if not tool or tool.phase != "pre_solve":
            continue
        try:
            result = tool.run({**context, **out})
            out["previous_outputs"][name] = result
            for k, v in result.items():
                if k != "previous_outputs":
                    out[k] = v
        except Exception as e:
            print(f"    [tool {name} failed: {str(e)[:80]}]")
    return out


def run_post_solve_tools(enabled_tools: list, context: dict) -> dict:
    """
    Run all enabled post_solve tools in registry order.
    May modify `code` in the returned dict.
    """
    out = dict(context)
    out.setdefault("previous_outputs", {})
    for name in enabled_tools:
        tool = get_tool(name)
        if not tool or tool.phase != "post_solve":
            continue
        try:
            result = tool.run(out)
            out["previous_outputs"][name] = result
            for k, v in result.items():
                if k != "previous_outputs":
                    out[k] = v
        except Exception as e:
            print(f"    [tool {name} failed: {str(e)[:80]}]")
    return out


def build_augmented_user_message(spec: str, tool_outputs: dict) -> str:
    """Combine spec + pre_solve tool outputs into the solver's user message."""
    parts = [f"Task specification:\n\n{spec}"]
    if "spec_analysis" in tool_outputs:
        parts.append(f"\nSpec analysis (from SpecAnalyzer tool):\n{tool_outputs['spec_analysis']}")
    if "edge_cases" in tool_outputs:
        parts.append(f"\nEdge cases to handle (from EdgeCasePredictor tool):\n{tool_outputs['edge_cases']}")
    parts.append("\nRespond with ONLY the implementation code in a code block. No explanation.")
    return "\n".join(parts)
