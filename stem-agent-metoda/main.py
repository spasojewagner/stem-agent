"""
Stem Agent - JetBrains AI Engineering Internship
Author: Marko Spasojevic

This stem agent has specialized into JavaScript code generation
(classes / modules implemented from vague specifications).

Usage:
  python main.py                          # interactive: type a JS prompt
  python main.py --prompt "Build a..."   # direct prompt (no typing)
  python main.py --scenario restaurant   # built-in scenario
  python main.py --domain "..."          # full stem exploration of a JS sub-domain
  python main.py --benchmark             # default known benchmark
"""

import os
import re
import sys
import copy
import json
import shutil
import argparse
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from evaluate import run_benchmark, build_tasks
from evolve import evolution_loop
from genome import DEFAULT_GENOME
from utils import save_json, print_banner


# --- SCOPE GUARD
# Prompts clearly outside JS class/module work get rejected.
# Word-boundary regex avoids false positives on common English words.

_OUT_OF_SCOPE_MARKERS = {
    "HTML/CSS frontend layout": [
        r"\bhtml\b",
        r"\bcss\b",
        r"\bwebpage\b",
        r"\blanding page\b",
        r"\bhero section\b",
        r"\bnavbar\b",
        r"\bstylesheet\b",
        r"\bresponsive design\b",
        r"\bcss grid\b",
        r"\bflexbox\b",
        r"\btailwind\b",
        r"\bbootstrap\b",
        r"\bmedia quer(y|ies)\b",
        r"<div\b",
        r"<html\b",
    ],
    "Python code": [
        r"\bpython\b",
        r"\bdjango\b",
        r"\bflask\b",
        r"\bfastapi\b",
        r"\bpytest\b",
        r"\bnumpy\b",
        r"\bpandas\b",
        r"\bpip install\b",
        r"\bjupyter\b",
        r"\.py\b",
    ],
    "SQL / database queries": [
        r"\bselect\s+\*\s+from\b",
        r"\binsert into\b",
        r"\bcreate table\b",
        r"\bdrop table\b",
        r"\bmysql\b",
        r"\bpostgres(ql)?\b",
        r"\bsqlite\b",
    ],
    "non-programming task (math/lifestyle/factual)": [
        r"\bcalorie(s)?\b",
        r"\brecipe\b",
        r"\bingredient(s)?\b",
        r"\bdistance from (the )?earth\b",
        r"\bdistance from (the )?moon\b",
        r"\bsolve this equation\b",
    ],
}


def check_scope(prompt: str) -> tuple:
    """
    Returns (in_scope: bool, detected_class: str | None, matched_pattern: str | None).
    """
    p = prompt.lower()
    for detected_class, patterns in _OUT_OF_SCOPE_MARKERS.items():
        for pat in patterns:
            if re.search(pat, p):
                return False, detected_class, pat
    return True, None, None


def reject_out_of_scope(prompt: str, detected_class: str, matched_pattern: str):
    """Print the rejection message using the task's own language and exit."""
    print("\n" + "=" * 60)
    print("  SCOPE CHECK FAILED")
    print("=" * 60)
    print(f"\n  This stem agent specializes in:")
    print(f"     JavaScript classes / modules implemented from vague specs")
    print(f"\n  Your prompt looks like:")
    print(f"     {detected_class}")
    print(f"     (matched marker: /{matched_pattern}/)")
    print(f"\n  From the task statement:")
    print(f'     "The end result isn\'t a universal agent. It\'s an agent that')
    print(f'      became specific -- through its own process. For a different')
    print(f'      class of tasks, you\'d start a new stem agent."')
    print(f"\n  Examples of in-scope prompts:")
    print(f"     > Build a shopping cart system")
    print(f"     > Implement a task queue with priorities")
    print(f"     > Create a notification manager")
    print(f"     > Build a simple bank account manager")
    print(f"     > Implement a rate limiter")
    print(f"\n  Or run the default benchmark:  python main.py --benchmark\n")
    sys.exit(2)


# --- OUTPUT FOLDER

def make_output_folder(label: str) -> str:
    slug = "".join(c if c.isalnum() or c == " " else "" for c in label[:40])
    slug = "_".join(slug.lower().split())[:35]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = os.path.join("output", f"{ts}_{slug}")
    os.makedirs(folder, exist_ok=True)
    return folder


# --- SAVE FINAL CODE

def save_final_code(task_id: str, best_genome: dict, output_folder: str):
    """Run agent one final time with evolved genome, save the JS code."""
    from agents.solver import solve_task
    from genome import genome_to_system_prompt
    from executor import extract_code, TASKS_DIR

    task_dir = os.path.join(TASKS_DIR, task_id)
    spec_file = os.path.join(task_dir, "spec.txt")
    tests_file = os.path.join(task_dir, "tests.js")

    if not os.path.exists(spec_file):
        print(f"  [Output] No spec found for {task_id}, skipping code save.")
        return

    with open(spec_file, encoding="utf-8") as f:
        spec = f.read()

    task = {"id": task_id, "spec": spec}
    system_prompt = genome_to_system_prompt(best_genome)

    print(f"\n  [Output] Generating final implementation with evolved genome...")
    try:
        response = solve_task(task, system_prompt)
        code = extract_code(response)

        n_strategies = len(best_genome.get("strategies", []))
        score = best_genome.get("score", 0)

        code_path = os.path.join(output_folder, f"{task_id}_implementation.js")
        with open(code_path, "w", encoding="utf-8") as f:
            f.write(f"// ===================================================\n")
            f.write(f"// Stem Agent -- Final Implementation\n")
            f.write(f"// Task:       {task_id}\n")
            f.write(f"// Strategies: {n_strategies} evolved by agent\n")
            f.write(f"// Score:      {score:.1%}\n")
            f.write(f"// ===================================================\n\n")
            f.write(code)

        print(f"  [Output] Implementation: {code_path}")

        if os.path.exists(tests_file):
            tests_dst = os.path.join(output_folder, f"{task_id}_tests.js")
            shutil.copy(tests_file, tests_dst)
            print(f"  [Output] Tests:          {tests_dst}")

        readme_path = os.path.join(output_folder, "HOW_TO_VERIFY.txt")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(f"How to verify the final implementation:\n\n")
            f.write(f"1. Copy implementation to solution slot:\n")
            f.write(f"   cp {code_path} {task_dir}/solution.js\n\n")
            f.write(f"2. Run the tests:\n")
            f.write(f"   node {tests_dst}\n\n")
            f.write(f"Expected score: {score:.1%}\n")

        print(f"  [Output] Instructions:   {readme_path}")

    except Exception as e:
        print(f"  [Output] Could not save final code: {e}")


# --- INTERACTIVE MODE

def interactive_prompt() -> str:
    print("\n" + "=" * 60)
    print("STEM AGENT -- Interactive Mode")
    print("=" * 60)
    print("\nScope: JavaScript classes and modules.")
    print("Out of scope: HTML/CSS, Python, SQL, math, lifestyle questions.")
    print("              (For those, the task says: start a different stem agent.)")
    print("\nExamples:")
    print("  > Build a shopping cart system")
    print("  > Implement a task queue with priorities")
    print("  > Create a notification manager")
    print("  > Build a simple bank account manager")
    print("  > Implement a rate limiter\n")
    prompt = input("Your prompt: ").strip()
    if not prompt:
        print("No prompt entered. Exiting.")
        sys.exit(0)
    return prompt


# --- BUILD TASKS FROM ANY PROMPT

def build_from_prompt(prompt: str) -> tuple:
    """
    Given an in-scope JS prompt:
    - Evaluator (gpt-4o) generates Node.js tests independently
    - Agent (gpt-4o-mini) will get only the spec
    Returns: (tasks, output_folder, task_id)
    """
    from evaluator import generate_tests_independently

    output_folder = make_output_folder(prompt)
    task_id = "task_interactive"
    tasks_dir = os.path.join(os.path.dirname(__file__), "benchmarks", "tasks")
    task_dir = os.path.join(tasks_dir, task_id)
    os.makedirs(task_dir, exist_ok=True)

    # Spec = exactly what user typed + JS export hint
    # (This is now safe because check_scope has already rejected non-JS prompts.)
    spec = prompt.strip()
    if "module.exports" not in spec and "export" not in spec.lower():
        spec += "\n\nExport the main class as: module.exports = { ClassName }"

    # Domain analysis -- inferred from prompt, gives evaluator edge-case hints
    domain_analysis = {
        "domain": prompt,
        "understanding": prompt,
        "specialized_agent_can": (
            "Handle all edge cases including empty inputs, invalid arguments, "
            "boundary values, duplicate operations, and concurrent state changes"
        ),
        "common_failure_modes": [
            "Missing input validation (null, undefined, empty)",
            "No error thrown for invalid operations",
            "Missing methods that a complete implementation needs",
            "State leaks between instances",
            "Off-by-one errors in size/capacity logic",
            "Not returning expected values (undefined instead of -1, null, etc.)",
            "Mutable state exposed directly (should return copies)",
        ]
    }

    with open(os.path.join(task_dir, "spec.txt"), "w", encoding="utf-8") as f:
        f.write(spec)

    tests_code = generate_tests_independently(spec, domain_analysis, task_id)

    with open(os.path.join(task_dir, "tests.js"), "w", encoding="utf-8") as f:
        f.write(tests_code)

    n_tests = tests_code.count("test(") - tests_code.count("function test(")

    meta = {
        "id": task_id,
        "type": "interactive",
        "difficulty": "auto",
        "description": prompt[:80],
        "spec": spec,
        "n_tests": n_tests
    }
    with open(os.path.join(task_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    with open(os.path.join(output_folder, "prompt.txt"), "w", encoding="utf-8") as f:
        f.write(prompt)
    with open(os.path.join(output_folder, "evaluator_tests.js"), "w", encoding="utf-8") as f:
        f.write("// Generated independently by evaluator (gpt-4o)\n")
        f.write("// Agent never saw these during evolution\n\n")
        f.write(tests_code)

    print(f"  [Evaluator] Tests saved to output folder (agent never saw these)")
    print(f"  [Output]    Folder: {output_folder}/")

    return [meta], output_folder, task_id


# --- MAIN

def main():
    parser = argparse.ArgumentParser(description="Stem Agent (JS specialization)")
    parser.add_argument("--prompt",    type=str, help="Direct prompt (skip interactive input)")
    parser.add_argument("--scenario",  type=str, help="Built-in scenario: restaurant")
    parser.add_argument("--domain",    type=str, help="Full domain exploration")
    parser.add_argument("--benchmark", action="store_true", help="Run default benchmark")
    parser.add_argument("--use-tools", action="store_true",
                        help="Enable tool registry: mutator can propose +tool / -tool mutations "
                             "in addition to natural-language strategies.")
    args = parser.parse_args()

    print_banner()
    model      = os.environ.get("OPENAI_MODEL",     "gpt-4o-mini")
    eval_model = os.environ.get("EVALUATOR_MODEL",  "gpt-4o")
    print(f"Agent model:     {model}  (implements from spec)")
    print(f"Evaluator model: {eval_model}  (generates tests independently)")
    print(f"Specialization:  JavaScript code generation from vague specs")
    if args.use_tools:
        from agents.tools import available_tools
        print(f"Tool registry:   ENABLED -- mutator may propose tools from {available_tools()}")

    os.makedirs("results", exist_ok=True)
    os.makedirs("state",   exist_ok=True)
    os.makedirs("output",  exist_ok=True)

    output_folder    = "output/default"
    task_id_for_save = None

    # --- Select mode
    if args.benchmark:
        tasks = build_tasks()
        output_folder = make_output_folder("benchmark")
        print(f"\nMode: DEFAULT BENCHMARK")

    elif args.scenario:
        from main_scenarios import build_scenario_tasks
        tasks, output_folder = build_scenario_tasks(args.scenario)
        task_id_for_save = f"task_{args.scenario}"
        print(f"\nMode: SCENARIO -- {args.scenario}")

    elif args.domain:
        from domain_explorer import explore_and_build
        # Scope check the domain string too
        in_scope, detected, matched = check_scope(args.domain)
        if not in_scope:
            reject_out_of_scope(args.domain, detected, matched)
        tasks = explore_and_build(args.domain)
        output_folder = make_output_folder(args.domain)
        print(f"\nMode: DOMAIN EXPLORATION -- {args.domain}")

    else:
        # Interactive or --prompt
        prompt = args.prompt if args.prompt else interactive_prompt()

        # Scope guard: reject prompts that belong to a different stem agent
        in_scope, detected, matched = check_scope(prompt)
        if not in_scope:
            reject_out_of_scope(prompt, detected, matched)

        tasks, output_folder, task_id_for_save = build_from_prompt(prompt)
        print(f"\nMode: INTERACTIVE")
        print(f"Prompt: {prompt[:80]}")

    total_tests = sum(t.get("n_tests", 10) for t in tasks)
    print(f"\nBenchmark:  {len(tasks)} task(s), ~{total_tests} tests")
    print(f"Agent knows: nothing (0 strategies)")
    print("=" * 60)

    # --- Baseline
    print("\nRunning BASELINE (agent: 0 strategies, 0 knowledge)...")
    baseline_results = run_benchmark(copy.deepcopy(DEFAULT_GENOME), tasks)
    baseline_score   = baseline_results["score"]
    print(f"Baseline score: {baseline_score:.1%}")
    save_json("results/baseline.json", baseline_results)

    # If baseline already blew up on infrastructure, bail with a clear message
    # instead of letting the evolution loop run 8 useless iterations.
    from evolve import _detect_fatal_error, _bail_on_fatal
    _fatal = _detect_fatal_error(baseline_results)
    if _fatal:
        _bail_on_fatal(_fatal)

    # --- Evolution
    best_genome, evolution_log = evolution_loop(tasks, tools_mode=args.use_tools)

    # --- Results
    final_score  = best_genome["score"]
    improvement  = final_score - baseline_score
    n_strategies = len(best_genome.get("strategies", []))

    print("\n" + "=" * 60)
    print("EVOLUTION COMPLETE")
    print("=" * 60)
    print(f"Baseline:    {baseline_score:.1%}  (0 strategies)")
    print(f"Final:       {final_score:.1%}  ({n_strategies} evolved strategies)")
    print(f"Improvement: {improvement:+.1%}")

    if best_genome.get("strategies"):
        print(f"\nWhat the agent learned:")
        for i, s in enumerate(best_genome["strategies"], 1):
            print(f"  {i}. {s}")

    print(f"\nLineage:")
    for it in evolution_log["iterations"]:
        mark = "[*]" if it["score"] == final_score else "   "
        mut  = it.get("mutation_applied", "")
        if mut and "DISCARDED" not in str(mut):
            print(f"{mark} Iter {it['iteration']}: {it['score']:.1%} | +\"{mut[:65]}\"")
        else:
            print(f"{mark} Iter {it['iteration']}: {it['score']:.1%}")

    # --- Save everything
    save_json("results/final_genome.json",    best_genome)
    save_json("results/evolution_log.json",   evolution_log)

    save_json(os.path.join(output_folder, "baseline.json"),      baseline_results)
    save_json(os.path.join(output_folder, "evolution_log.json"), evolution_log)
    save_json(os.path.join(output_folder, "final_genome.json"),  best_genome)
    save_json(os.path.join(output_folder, "summary.json"), {
        "prompt":         tasks[0].get("spec", "")[:300] if tasks else "",
        "baseline_score": baseline_score,
        "final_score":    final_score,
        "improvement":    improvement,
        "n_strategies":   n_strategies,
        "strategies":     best_genome.get("strategies", []),
        "lineage": [
            {"iteration": it["iteration"], "score": it["score"],
             "mutation": it.get("mutation_applied", "")}
            for it in evolution_log["iterations"]
        ]
    })

    if task_id_for_save:
        save_final_code(task_id_for_save, best_genome, output_folder)

    print(f"\nOutput folder: {output_folder}/")
    print(f"   prompt.txt                  your original prompt")
    print(f"   evaluator_tests.js          tests agent never saw")
    print(f"   task_*_implementation.js    final generated code")
    print(f"   task_*_tests.js             tests (copy alongside impl to run)")
    print(f"   HOW_TO_VERIFY.txt           instructions to run tests")
    print(f"   summary.json                scores + lineage")
    print(f"   evolution_log.json          full details")


if __name__ == "__main__":
    main()
