"""
Domain Explorer -- the stem cell phase.

Given only a domain name, the agent figures out:
  1. What kinds of problems exist in this domain
  2. What a good benchmark looks like
  3. What skills are needed

Key improvements from v6:
  - spec and tests generated with SEPARATE models (agent=gpt-4o-mini, evaluator=gpt-4o)
  - task_types are concrete class names, not abstract concepts
  - evaluator sees domain failure modes, agent does not
"""

import os
import json
import requests
from evaluator import generate_tests_independently


def _call_llm(prompt: str, max_tokens: int = 3000, temperature: float = 0.3) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=60
    )
    content = response.json()["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        if content.startswith("json"):
            content = content[4:].strip()
    return content


def explore_domain(domain: str) -> dict:
    print(f"\n  [Explorer] Analyzing domain: '{domain}'")

    prompt = f"""You are a stem agent specializing in JavaScript software engineering.

Domain to analyze: {domain}

Identify the key software components needed. Use CONCRETE class names.

Respond ONLY with JSON (no markdown):
{{
  "domain": "{domain}",
  "understanding": "2-3 sentence description",
  "task_types": ["ConcreteClassName1", "ConcreteClassName2", "ConcreteClassName3"],
  "minimal_agent_can": "what raw LLM does without special skills",
  "specialized_agent_can": "what skilled implementation handles that minimal misses",
  "common_failure_modes": [
    "specific failure 1",
    "specific failure 2", 
    "specific failure 3",
    "specific failure 4"
  ],
  "skills_needed": ["skill1", "skill2", "skill3"]
}}

For task_types use concrete names like "Order", "OrderManager", "MenuItem"
NOT abstract names like "data processing" or "optimization"."""

    content = _call_llm(prompt, temperature=0.2)
    try:
        analysis = json.loads(content)
        print(f"  [Explorer] Domain understood: {analysis['understanding'][:80]}...")
        print(f"  [Explorer] Components: {', '.join(analysis['task_types'][:3])}")
        print(f"  [Explorer] Key failures: {', '.join(analysis['common_failure_modes'][:2])}")
        return analysis
    except Exception as e:
        print(f"  [Explorer] Parse error: {e}")
        return {
            "domain": domain,
            "understanding": domain,
            "task_types": ["MainClass"],
            "minimal_agent_can": "implement basic functionality",
            "specialized_agent_can": "handle edge cases and validation",
            "common_failure_modes": ["missing validation", "no error handling"],
            "skills_needed": ["validation", "edge case handling"]
        }


def generate_task_with_evaluator(domain: str, class_name: str, analysis: dict, task_index: int) -> dict:
    """
    Agent gets vague spec only.
    Evaluator independently generates tests using stronger model.
    """
    print(f"\n  [Explorer] Defining task {task_index}: '{class_name}'")

    spec_prompt = f"""Write a SHORT spec for a JavaScript class called {class_name}.

Context: {domain}

Rules:
- 2-4 sentences ONLY
- Describe WHAT it does, not HOW  
- Do NOT mention specific methods or edge cases
- End with exactly: Export as: module.exports = {{ {class_name} }}

Respond with ONLY the spec text."""

    spec = _call_llm(spec_prompt, max_tokens=200, temperature=0.4)
    print(f"  [Explorer] Spec (agent sees this): {spec[:100]}...")

    task_id = f"task_explored_{task_index}"
    tests_code = generate_tests_independently(spec, analysis, task_id)
    n_tests = tests_code.count("test(") + tests_code.count("testAsync(")

    return {
        "spec": spec,
        "tests_code": tests_code,
        "class_name": class_name,
        "n_tests": n_tests
    }


def explore_and_build(domain: str, n_tasks: int = 3) -> list:
    print(f"\n{'='*60}")
    print(f"DOMAIN EXPLORATION: {domain}")
    print(f"{'='*60}")

    analysis = explore_domain(domain)
    class_names = analysis["task_types"][:n_tasks]
    tasks = []
    tasks_dir = os.path.join(os.path.dirname(__file__), "benchmarks", "tasks")

    for i, class_name in enumerate(class_names):
        task_data = generate_task_with_evaluator(domain, class_name, analysis, i + 1)
        task_id = f"task_explored_{i+1}"
        task_dir = os.path.join(tasks_dir, task_id)
        os.makedirs(task_dir, exist_ok=True)

        with open(os.path.join(task_dir, "spec.txt"), "w", encoding="utf-8") as f:
            f.write(task_data["spec"])
        with open(os.path.join(task_dir, "tests.js"), "w", encoding="utf-8") as f:
            f.write(task_data["tests_code"])

        meta = {
            "id": task_id,
            "type": class_name,
            "difficulty": "auto-generated",
            "description": f"{domain} — {class_name}",
            "domain": domain
        }
        with open(os.path.join(task_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        meta["spec"] = task_data["spec"]
        meta["n_tests"] = task_data["n_tests"]
        tasks.append(meta)

    print(f"\n  [Explorer] {len(tasks)} tasks created")
    print(f"  [Explorer] Agent sees: specs only")
    print(f"  [Explorer] Evaluator generated: tests independently\n")

    os.makedirs("results", exist_ok=True)
    with open("results/domain_analysis.json", "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2)

    return tasks
