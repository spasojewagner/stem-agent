"""
Execution Engine -- runs agent's proposed fix through real Node.js tests.
Real pass/fail based on actual code execution.
"""

import os
import re
import subprocess
import json

TASKS_DIR = os.path.join(os.path.dirname(__file__), "benchmarks", "tasks")


def extract_code(response: str) -> str:
    patterns = [
        r"```(?:javascript|js)\n(.*?)```",
        r"```\n(.*?)```",
    ]
    for pattern in patterns:
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
    return response.strip()


def run_task(task_id: str, agent_response: str) -> dict:
    task_dir = os.path.join(TASKS_DIR, task_id)
    tests_file = os.path.join(task_dir, "tests.js")

    if not os.path.exists(tests_file):
        return {"passed": False, "score": 0.0, "n_passed": 0, "n_failed": 0,
                "output": "", "error": f"Tests not found: {tests_file}"}

    solution_code = extract_code(agent_response)
    if not solution_code or len(solution_code) < 10:
        return {"passed": False, "score": 0.0, "n_passed": 0, "n_failed": 0,
                "output": "", "error": "Could not extract code from response"}

    solution_file = os.path.join(task_dir, "solution.js")
    try:
        with open(solution_file, "w", encoding="utf-8") as f:
            f.write(solution_code)

        result = subprocess.run(
            ["node", tests_file],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,          # 30s handles async tests (PromisePool uses setTimeout)
            cwd=task_dir,
            env={**os.environ, "PYTHONUTF8": "1"}
        )

        output = result.stdout + result.stderr

        # Count [PASS] and [FAIL] lines directly — works for all test formats
        n_passed = output.count("[PASS]")
        n_failed = output.count("[FAIL]")

        # Fallback to "X passed, Y failed" summary line
        if n_passed == 0 and n_failed == 0:
            import re as _re
            pm = _re.search(r"(\d+) passed", output)
            fm = _re.search(r"(\d+) failed", output)
            n_passed = int(pm.group(1)) if pm else 0
            n_failed = int(fm.group(1)) if fm else 0

        # If still nothing — tests crashed before any test ran
        if n_passed == 0 and n_failed == 0 and result.returncode != 0:
            # Extract error for mutator to see
            error_line = next(
                (l for l in output.split("\n") if "Error" in l or "error" in l),
                "Tests crashed before running"
            )
            return {
                "passed": False,
                "score": 0.0,
                "n_passed": 0,
                "n_failed": 1,
                "output": output,
                "error": error_line[:200]
            }

        total = n_passed + n_failed
        score = n_passed / total if total > 0 else 0.0
        passed = result.returncode == 0 and n_failed == 0

        return {
            "passed": passed,
            "score": score,
            "n_passed": n_passed,
            "n_failed": n_failed,
            "output": output,
            "error": None
        }

    except subprocess.TimeoutExpired:
        return {"passed": False, "score": 0.0, "n_passed": 0, "n_failed": 0,
                "output": "", "error": "Timeout (30s) — possible infinite loop"}
    except FileNotFoundError:
        return {"passed": False, "score": 0.0, "n_passed": 0, "n_failed": 0,
                "output": "", "error": "Node.js not found"}
    except Exception as e:
        return {"passed": False, "score": 0.0, "n_passed": 0, "n_failed": 0,
                "output": "", "error": str(e)}
    finally:
        if os.path.exists(solution_file):
            os.remove(solution_file)


def get_all_task_ids(include_explored: bool = False) -> list:
    if not os.path.exists(TASKS_DIR):
        return []
    all_ids = sorted([
        d for d in os.listdir(TASKS_DIR)
        if os.path.isdir(os.path.join(TASKS_DIR, d)) and d.startswith("task_")
    ])
    if include_explored:
        return all_ids
    # Default benchmark: exclude auto-generated and custom tasks
    return [t for t in all_ids if not t.startswith("task_explored") and t != "task_custom"]


def run_custom_task(spec: str, code: str) -> dict:
    """
    For custom tasks without pre-written tests.
    Uses LLM to evaluate correctness against the spec.
    Returns a score 0.0-1.0.
    """
    import requests
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    prompt = f"""You are evaluating a JavaScript implementation against a spec.

SPEC:
{spec}

CODE:
{code}

Evaluate how completely and correctly the code implements the spec.
Consider: all required methods present, correct behavior, edge cases, exports correct.

Respond ONLY with JSON:
{{"score": 0.0, "passed": [], "failed": [], "notes": ""}}

Where score is 0.0 to 1.0, passed/failed are lists of spec requirements."""

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "max_tokens": 400,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        content = response.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        result = json.loads(content.strip())
        score = float(result.get("score", 0.0))
        passed = result.get("passed", [])
        failed = result.get("failed", [])
        notes = result.get("notes", "")
        output = f"LLM Judge score: {score:.1%}\n"
        if passed:
            output += "  Passed: " + ", ".join(passed) + "\n"
        if failed:
            output += "  Failed: " + ", ".join(failed) + "\n"
        if notes:
            output += f"  Notes: {notes}\n"
        return {
            "passed": score >= 0.8,
            "score": score,
            "n_passed": len(passed),
            "n_failed": len(failed),
            "output": output,
            "error": None
        }
    except Exception as e:
        return {"passed": False, "score": 0.0, "n_passed": 0, "n_failed": 1,
                "output": "", "error": str(e)}


def generate_tests_for_spec(spec: str) -> str:
    """
    Given a vague spec, generate a tests.js file that covers
    basic functionality AND edge cases the spec doesn't mention.
    The agent will never see these tests -- it must predict them.
    """
    import requests
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    prompt = f"""You are writing Node.js tests for a JavaScript class.

SPEC:
{spec}

Write a tests.js file that:
1. Tests all methods mentioned in the spec (basic happy path)
2. Tests edge cases the spec does NOT explicitly mention (e.g. empty state, overwrite, error handling, return values)
3. Uses this exact test harness (no Jest, no require of test framework):

const {{ ClassName }} = require('./solution.js');
let passed = 0; let failed = 0;
function test(name, fn) {{
  try {{ fn(); console.log(`  [PASS] ${{name}}`); passed++; }}
  catch(e) {{ console.log(`  [FAIL] ${{name}}: ${{e.message}}`); failed++; }}
}}
function assert(c, m) {{ if (!c) throw new Error(m || 'assertion failed'); }}

// tests here...

console.log(`\\nResults: ${{passed}} passed, ${{failed}} failed`);
process.exit(failed > 0 ? 1 : 0);

CRITICAL RULES for test generation:
- ONLY test methods/properties explicitly mentioned in the spec
- Do NOT invent methods that the spec does not mention (e.g. setLimit, reset, clear)
- Edge cases must be reachable with the API described in the spec
- If the spec says "allow max N calls per second", test ONLY the allow() behavior

Write at least 8 tests. Replace ClassName with the actual class name from the spec.
Respond with ONLY the complete tests.js code, no explanation."""

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "max_tokens": 1500,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=30
    )
    content = response.json()["choices"][0]["message"]["content"].strip()
    # Strip markdown fences if present
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    return content
