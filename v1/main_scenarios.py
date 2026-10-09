"""
Built-in scenarios — pre-defined prompts with rich domain analysis.
Use: python main.py --scenario restaurant
"""

import os
import json
import shutil
from evaluator import generate_tests_independently
from utils import save_json


SCENARIOS = {
    "restaurant": {
        "spec": """Build a restaurant order management system in JavaScript.

A restaurant needs to manage customer orders from creation to delivery.
Orders contain items, have a status that progresses through stages,
and need to be tracked by the kitchen and serving staff.

Export as: module.exports = { OrderManager }""",

        "domain_analysis": {
            "domain": "restaurant order management",
            "understanding": "Managing the full lifecycle of restaurant orders from placement to delivery.",
            "specialized_agent_can": "Enforce valid status transitions, prevent invalid operations, calculate totals, handle concurrent orders",
            "common_failure_modes": [
                "Missing status transition validation (can skip from pending to delivered)",
                "No total price calculation",
                "Status going backwards (delivered back to pending)",
                "No order lookup by ID",
                "No handling for empty or invalid orders",
                "Direct mutation of order items allowed",
                "No tracking of multiple simultaneous orders"
            ],
            "skills_needed": ["state machine", "immutable item management", "price aggregation", "multi-order registry"]
        }
    }
}


def build_scenario_tasks(scenario: str):
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario}'. Available: {list(SCENARIOS.keys())}")

    data = SCENARIOS[scenario]
    spec = data["spec"]
    analysis = data["domain_analysis"]

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_folder = os.path.join("output", f"{timestamp}_{scenario}")
    os.makedirs(output_folder, exist_ok=True)

    tasks_dir = os.path.join(os.path.dirname(__file__), "benchmarks", "tasks")
    task_id = f"task_{scenario}"
    task_dir = os.path.join(tasks_dir, task_id)
    os.makedirs(task_dir, exist_ok=True)

    print(f"\n  [Scenario] {scenario}")
    print(f"  [Scenario] Spec (agent sees this only):")
    for line in spec.strip().split("\n"):
        print(f"    {line}")

    with open(os.path.join(task_dir, "spec.txt"), "w", encoding="utf-8") as f:
        f.write(spec)

    print(f"\n  [Evaluator] Generating tests independently...")
    tests_code = generate_tests_independently(spec, analysis, task_id)
    with open(os.path.join(task_dir, "tests.js"), "w", encoding="utf-8") as f:
        f.write(tests_code)

    n_tests = tests_code.count("test(") + tests_code.count("testAsync(")

    meta = {
        "id": task_id,
        "type": "scenario",
        "difficulty": "hard",
        "description": f"Scenario: {scenario}",
        "spec": spec,
        "n_tests": n_tests
    }
    with open(os.path.join(task_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    # Save to output folder
    with open(os.path.join(output_folder, "prompt.txt"), "w", encoding="utf-8") as f:
        f.write(spec)
    with open(os.path.join(output_folder, "evaluator_tests.js"), "w", encoding="utf-8") as f:
        f.write(f"// Tests generated independently by evaluator\n// Agent never saw these\n\n")
        f.write(tests_code)

    print(f"  [Evaluator] {n_tests} tests generated. Agent never sees these.\n")

    os.makedirs("results", exist_ok=True)
    with open("results/domain_analysis.json", "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2)

    return [meta], output_folder
