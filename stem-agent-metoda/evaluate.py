"""
Evaluate -- runs all benchmark tasks with a given genome.
Uses real Node.js execution for pass/fail.
"""
import os
from genome import genome_to_system_prompt, describe_genome
from agents.solver import solve_task
from executor import run_task, get_all_task_ids

TASKS_DIR = os.path.join(os.path.dirname(__file__), "benchmarks", "tasks")


def build_tasks(task_ids: list = None) -> list:
    import json
    tasks = []
    ids = task_ids if task_ids else get_all_task_ids()
    for task_id in ids:
        task_dir = os.path.join(TASKS_DIR, task_id)
        try:
            with open(os.path.join(task_dir, "metadata.json")) as f:
                meta = json.load(f)

            # Load spec file (primary) or fall back to question field
            spec_file = os.path.join(task_dir, "spec.txt")
            if os.path.exists(spec_file):
                with open(spec_file) as f:
                    meta["spec"] = f.read().strip()
            
            tasks.append(meta)
        except Exception as e:
            print(f"  [Warning] Could not load task {task_id}: {e}")
    return tasks


def run_benchmark(genome: dict, tasks: list, verbose: bool = True) -> dict:
    system_prompt = genome_to_system_prompt(genome)
    genome_desc = describe_genome(genome)

    if verbose:
        print(f"\n  Running: {genome_desc}")

    results = []
    total_tests_passed = 0
    total_tests = 0
    task_scores = []

    for task in tasks:
        task_id = task["id"]
        if verbose:
            print(f"  Task [{task_id}]... ", end="", flush=True)

        try:
            enabled_tools = genome.get("tools", [])
            response = solve_task(task, system_prompt, enabled_tools=enabled_tools)
            execution = run_task(task_id, response)

            n_passed = execution.get("n_passed", 0)
            n_failed = execution.get("n_failed", 0)
            n_total = n_passed + n_failed
            task_score = n_passed / n_total if n_total > 0 else 0.0

            total_tests_passed += n_passed
            total_tests += n_total
            task_scores.append(task_score)

            if execution["passed"]:
                if verbose:
                    print(f"[OK] {n_passed}/{n_total} tests")
            else:
                exec_err = execution.get("error", "")
                if verbose:
                    if exec_err and n_total <= 1:
                        print(f"[CRASH] {exec_err[:80]}")
                    else:
                        print(f"[PARTIAL] {n_passed}/{n_total} tests")
                if verbose and execution.get("output"):
                    for line in execution["output"].split("\n"):
                        if "[FAIL]" in line:
                            print(f"         {line.strip()}")

            results.append({
                "task_id": task_id,
                "type": task.get("type"),
                "passed": execution["passed"],
                "score": task_score,
                "n_passed": n_passed,
                "n_failed": n_failed,
                "test_output": execution.get("output", "")[:600],
                "error": execution.get("error")
            })

        except Exception as e:
            if verbose:
                print(f"[ERROR] {e}")
            task_scores.append(0.0)
            results.append({
                "task_id": task_id,
                "passed": False,
                "score": 0.0,
                "n_passed": 0,
                "n_failed": 0,
                "error": str(e)
            })

    # Score = average test pass rate across all tasks
    overall_score = sum(task_scores) / len(task_scores) if task_scores else 0.0

    if verbose:
        print(f"  Score: {overall_score:.1%} ({total_tests_passed}/{total_tests} tests across {len(tasks)} tasks)")

    return {
        "genome": genome,
        "genome_description": genome_desc,
        "score": overall_score,
        "total_tests_passed": total_tests_passed,
        "total_tests": total_tests,
        "task_results": results
    }


def build_custom_task(spec: str) -> dict:
    """Build a custom task: generate tests.js from spec, then use real Node.js execution."""
    import os
    from executor import generate_tests_for_spec

    print("  Generating tests for custom spec...")
    tests_code = generate_tests_for_spec(spec)

    # Save tests to a temp task directory
    task_dir = os.path.join(os.path.dirname(__file__), "benchmarks", "tasks", "task_custom")
    os.makedirs(task_dir, exist_ok=True)

    tests_path = os.path.join(task_dir, "tests.js")
    with open(tests_path, "w", encoding="utf-8") as f:
        f.write(tests_code)

    # Count tests
    n_tests = tests_code.count("test(")
    print(f"  Generated {n_tests} tests for custom spec")

    return {
        "id": "task_custom",
        "type": "custom",
        "difficulty": "unknown",
        "spec": spec,
    }
