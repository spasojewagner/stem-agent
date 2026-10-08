"""
Evolution Loop -- iteratively evolves the genome's strategy list.
"""

import copy
import sys
from genome import DEFAULT_GENOME, apply_mutation, describe_genome
from evaluate import run_benchmark
from agents.mutator import suggest_mutation, record_discarded
from utils import save_json

MAX_ITERATIONS = 8
SUCCESS_THRESHOLD = 1.0
PLATEAU_PATIENCE = 3

# Substrings that signal "this is an infrastructure error, not a real test
# failure" -- evolution should stop, not invent fake strategies in response.
_INFRA_ERROR_MARKERS = (
    "API error 401",
    "API error 403",
    "API error 404",
    "API error 429",
    "API error 500",
    "API error 502",
    "API error 503",
    "Missing scopes",
    "insufficient permissions",
    "invalid_api_key",
    "rate_limit",
    "Connection refused",
    "Timeout",
    "connection error",
)


def _detect_fatal_error(results: dict):
    """
    If every task in the benchmark failed with an infrastructure error
    (API key wrong, model not allowed, network down, etc), return the
    first error message. Otherwise return None.

    Real test failures don't trip this -- only infra errors do.
    """
    task_results = results.get("task_results", [])
    if not task_results:
        return None

    fatal_errors = []
    for t in task_results:
        # A "real" failed test has n_passed + n_failed > 0 from actual asserts.
        # An infra failure has 0/0 plus an "error" string with an API marker.
        n_passed = t.get("n_passed", 0)
        n_failed = t.get("n_failed", 0)
        err = (t.get("error") or "") + " " + (t.get("test_output") or "")

        if n_passed == 0 and n_failed == 0 and any(m in err for m in _INFRA_ERROR_MARKERS):
            fatal_errors.append(err.strip())

    if len(fatal_errors) == len(task_results):
        return fatal_errors[0]
    return None


def _bail_on_fatal(error_msg: str):
    print("\n" + "=" * 60)
    print("FATAL ERROR -- stopping evolution loop")
    print("=" * 60)
    print(f"\nEvery task failed with the same infrastructure error.")
    print(f"This is NOT a real test failure -- the agent never got a chance to run.")
    print(f"\nFirst error returned:")
    print(f"  {error_msg[:400]}")
    print(f"\nLikely causes and fixes:")
    print(f"  - The API key in .env doesn't have permission for OPENAI_MODEL.")
    print(f"    Try setting OPENAI_MODEL=gpt-4o-mini in .env (widely permitted).")
    print(f"  - JetBrains-issued keys are usually scoped to specific models.")
    print(f"    If you got the key from Denis, only gpt-4o family is likely allowed.")
    print(f"  - Check OpenAI org roles: Reader/Writer/Owner must include 'model.request'.")
    print(f"  - For rate-limit errors, wait a minute and try again.")
    print(f"\nNo iterations performed. No credits wasted on fake evolution.")
    sys.exit(1)


def evolution_loop(benchmark_tasks: list, tools_mode: bool = False):
    current_genome = copy.deepcopy(DEFAULT_GENOME)
    best_genome = copy.deepcopy(DEFAULT_GENOME)

    evolution_log = {
        "iterations": [],
        "best_score": 0.0,
        "stop_reason": None
    }

    no_improvement_count = 0

    print("\n" + "="*60)
    print("EVOLUTION LOOP STARTED")
    print(f"Max iterations: {MAX_ITERATIONS}")
    print(f"Success threshold: {SUCCESS_THRESHOLD:.0%}")
    print(f"Tools mode: {'ON (mutator can propose tool changes)' if tools_mode else 'OFF (strategy-only)'}")
    print("="*60)

    for iteration in range(MAX_ITERATIONS):
        print(f"\nIteration {iteration + 1}/{MAX_ITERATIONS}")
        print(f"   Strategies: {len(current_genome.get('strategies', []))}")

        results = run_benchmark(current_genome, benchmark_tasks)
        score = results["score"]
        current_genome["score"] = score

        # If everything blew up on infrastructure (bad key, wrong model,
        # network), don't pretend to evolve -- bail with a clear message.
        fatal = _detect_fatal_error(results)
        if fatal:
            _bail_on_fatal(fatal)

        iteration_data = {
            "iteration": iteration + 1,
            "genome": describe_genome(current_genome),
            "genome_strategies": list(current_genome.get("strategies", [])),
            "score": score,
            "failures": results.get("failures_by_type", {}),
            "mutation_applied": None
        }

        if score > best_genome["score"]:
            best_genome = copy.deepcopy(current_genome)
            save_json("state/best_agent.json", best_genome)
            print(f"   [best] {score:.1%}")
            no_improvement_count = 0
        else:
            no_improvement_count += 1
            print(f"   No improvement ({no_improvement_count}/{PLATEAU_PATIENCE})")

        if score >= SUCCESS_THRESHOLD:
            print(f"\nSUCCESS THRESHOLD REACHED ({score:.1%} >= {SUCCESS_THRESHOLD:.0%})")
            iteration_data["stop_reason"] = "success_threshold"
            evolution_log["iterations"].append(iteration_data)
            evolution_log["stop_reason"] = "success_threshold"
            break

        if no_improvement_count >= PLATEAU_PATIENCE:
            print(f"\nPLATEAU -- no improvement for {PLATEAU_PATIENCE} iterations")
            iteration_data["stop_reason"] = "plateau"
            evolution_log["iterations"].append(iteration_data)
            evolution_log["stop_reason"] = "plateau"
            break

        # Ask LLM to invent a new strategy or propose a tool change
        print(f"   Failures: {results.get('failures_by_type', {})}")
        mutation = suggest_mutation(
            current_genome,
            score,
            results.get("failures_by_type", {}),
            results.get("task_results", []),
            tools_mode=tools_mode
        )

        new_strategy = mutation.get("strategy")
        reason       = mutation.get("reason", "")
        remove       = mutation.get("remove")
        add_tool     = mutation.get("add_tool")
        remove_tool  = mutation.get("remove_tool")

        # Determine what kind of mutation this is (for logging)
        if add_tool:
            mutation_label = f"+tool:{add_tool}"
            print(f"   [tool+] {add_tool}")
        elif remove_tool:
            mutation_label = f"-tool:{remove_tool}"
            print(f"   [tool-] {remove_tool}")
        elif new_strategy:
            mutation_label = new_strategy
            print(f"   New strategy: \"{new_strategy[:60]}\"")
            if remove:
                print(f"   Removing: \"{remove[:50]}\"")
        else:
            mutation_label = "no-op"
            print(f"   Mutator returned nothing actionable")

        print(f"   Reason: {reason}")

        candidate_genome = apply_mutation(
            current_genome,
            new_strategy=new_strategy,
            remove=remove,
            add_tool=add_tool,
            remove_tool=remove_tool,
        )

        n_strats = len(candidate_genome["strategies"])
        n_tools  = len(candidate_genome.get("tools", []))
        print(f"   Testing candidate (v{candidate_genome['version']}, "
              f"{n_strats} strategies, {n_tools} tools)...")
        candidate_results = run_benchmark(candidate_genome, benchmark_tasks)
        candidate_score = candidate_results["score"]
        candidate_genome["score"] = candidate_score

        if candidate_score >= score:
            print(f"   Promoted: {score:.1%} -> {candidate_score:.1%}")
            current_genome = candidate_genome
            iteration_data["mutation_applied"] = mutation_label
            iteration_data["mutation_reason"]  = reason
            iteration_data["candidate_score"]  = candidate_score
            no_improvement_count = 0
            # If the promoted candidate exceeds the best score, save it now
            # so the final summary reflects it even if the loop ends next.
            if candidate_score > best_genome["score"]:
                best_genome = copy.deepcopy(candidate_genome)
                save_json("state/best_agent.json", best_genome)
                print(f"   [best from candidate] {candidate_score:.1%}")
        else:
            print(f"   Discarded ({candidate_score:.1%} < {score:.1%}), keeping current")
            # Record discarded mutation
            if new_strategy:
                record_discarded(strategy=new_strategy)
            if add_tool:
                record_discarded(tool=add_tool)
            iteration_data["mutation_applied"] = f"DISCARDED: {mutation_label}"
            iteration_data["candidate_score"]  = candidate_score
            no_improvement_count += 1

        save_json("state/current_agent.json", current_genome)
        evolution_log["iterations"].append(iteration_data)
        save_json("results/evolution_log.json", evolution_log)

    evolution_log["best_score"] = best_genome["score"]
    if not evolution_log.get("stop_reason"):
        evolution_log["stop_reason"] = "max_iterations"

    print("\n" + "="*60)
    print("EVOLUTION SUMMARY")
    print("="*60)
    for it in evolution_log["iterations"]:
        marker = "[*]" if it["score"] == best_genome["score"] else "  "
        print(f"{marker} Iter {it['iteration']}: score={it['score']:.1%} | strategies={len(it.get('genome_strategies', []))}")
        if it.get("mutation_applied") and not it["mutation_applied"].startswith("DISCARDED"):
            print(f"     + \"{it['mutation_applied'][:70]}\"")

    return best_genome, evolution_log
