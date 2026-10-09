"""
Genome -- free-form strategy list + optional tool set.

The genome at version 1 is minimal. It declares the class of problems
the agent has chosen (JavaScript code generation from vague specs) and
has zero strategies and zero tools.

Two things can evolve:

  strategies -- natural-language instructions the agent's system prompt
                will include.

  tools      -- optional pipeline components from agents/tools.py that
                wrap the solver's call: pre-solve analysis, post-solve
                critique, post-solve method-alias injection, etc.

Both are mutated by the mutator. The mutator can propose a strategy
mutation OR a tool mutation each iteration.
"""
import copy

DEFAULT_GENOME = {
    "strategies": [],
    "tools": [],
    "version": 1,
    "score": 0.0,
    "mutations_history": []
}


def apply_mutation(genome: dict,
                   new_strategy: str = None,
                   remove: str = None,
                   add_tool: str = None,
                   remove_tool: str = None) -> dict:
    """
    Returns a new genome with the requested mutation(s) applied.
    Any combination of new_strategy / remove / add_tool / remove_tool is allowed.
    """
    candidate = copy.deepcopy(genome)
    strategies = list(candidate["strategies"])
    tools      = list(candidate.get("tools", []))
    history    = list(candidate.get("mutations_history", []))

    if remove:
        strategies = [s for s in strategies if s != remove]
        history.append(f"-strategy[{remove[:50]}]")

    if new_strategy and new_strategy not in strategies:
        strategies.append(new_strategy)
        history.append(f"+strategy[{new_strategy[:50]}]")

    if remove_tool and remove_tool in tools:
        tools.remove(remove_tool)
        history.append(f"-tool[{remove_tool}]")

    if add_tool and add_tool not in tools:
        tools.append(add_tool)
        history.append(f"+tool[{add_tool}]")

    candidate["strategies"]        = strategies
    candidate["tools"]             = tools
    candidate["mutations_history"] = history
    candidate["version"]           = genome["version"] + 1
    candidate["score"]             = 0.0
    return candidate


def genome_to_system_prompt(genome: dict) -> str:
    """
    Build the system prompt for the solver from the current genome.

    The base declares the chosen specialization (JS code generation).
    Strategies are appended as instructions the agent has evolved for itself.

    NOTE: tools are NOT mentioned in the system prompt. Tools wrap the
    solver's call externally (pre/post hooks in agents/tools.py).
    """
    base = (
        "You are a JavaScript engineer that implements classes and modules from "
        "specifications.\n"
        "You receive a vague spec; you must predict every method, edge case, and "
        "behavior\n"
        "a complete implementation needs. You never see the tests that will "
        "evaluate you.\n\n"
    )

    strategies = genome.get("strategies", [])

    if not strategies:
        return base + "Respond with ONLY the implementation code in a code block. No explanation."

    instructions = base + "Before writing your solution, apply these strategies you have learned:\n\n"
    for i, s in enumerate(strategies, 1):
        instructions += f"{i}. {s}\n"
    instructions += "\nThen respond with ONLY the implementation code in a code block. No explanation."
    return instructions


def describe_genome(genome: dict) -> str:
    strategies = genome.get("strategies", [])
    tools      = genome.get("tools", [])
    parts = []
    if strategies:
        short = [s[:40] + "..." if len(s) > 40 else s for s in strategies]
        parts.append(" | ".join(short))
    if tools:
        parts.append("tools=[" + ",".join(tools) + "]")
    if not parts:
        return f"v{genome['version']}: Raw LLM (no strategies, no tools)"
    return f"v{genome['version']}: [{' | '.join(parts)}]"
