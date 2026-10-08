"""
Independent Evaluator -- generates Node.js tests independently from the agent.

The evaluator (gpt-4o by default) reads the same spec the agent reads,
plus a domain analysis with failure modes the agent never sees,
and writes Node.js tests independently.

The agent (gpt-4o-mini by default) never sees these tests during evolution.
This is the architectural decision that prevents the agent from gaming
its own benchmark.
"""

import os
import requests


def _call_llm(prompt: str, model: str, max_tokens: int = 2000, temperature: float = 0.2) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
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
    if response.status_code != 200:
        raise Exception(f"Evaluator API error {response.status_code}: {response.text[:200]}")

    content = response.json()["choices"][0]["message"]["content"].strip()
    # Strip markdown fences (gpt-4o sometimes adds them despite being told not to)
    for fence in ["```javascript", "```js", "```"]:
        if content.startswith(fence):
            content = content[len(fence):]
            break
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def generate_tests_independently(spec: str, domain_analysis: dict, task_id: str) -> str:
    """
    Generate exactly 8 Node.js tests from the spec.

    The agent never sees these tests during evolution. It only sees the spec
    and must predict what a complete implementation needs.
    """
    evaluator_model = os.environ.get("EVALUATOR_MODEL", "gpt-4o")
    failure_modes = domain_analysis.get("common_failure_modes", [])[:3]
    specialized = domain_analysis.get(
        "specialized_agent_can",
        "handle edge cases correctly"
    )

    print(f"  [Evaluator] Generating JavaScript tests from spec (model: {evaluator_model})")
    tests_code = _generate_javascript_tests(spec, specialized, failure_modes, evaluator_model)

    # Safety net: ensure the tests file always exits with a clean code
    if "process.exit" not in tests_code:
        tests_code += (
            "\nconsole.log(`\\nResults: ${passed} passed, ${failed} failed`);"
            "\nprocess.exit(failed > 0 ? 1 : 0);"
        )

    # Rough count -- "test(" minus the harness definition
    n_tests = tests_code.count("test(") - tests_code.count("function test(")
    print(f"  [Evaluator] {n_tests} tests generated (agent never sees these)")
    return tests_code


def _generate_javascript_tests(spec: str, specialized: str, failure_modes: list, model: str) -> str:
    prompt = """You are writing Node.js tests for a JavaScript class or module.

SPECIFICATION (agent received this):
""" + spec + """

A complete implementation handles:
""" + specialized + """

Edge cases to verify:
""" + "\n".join("- " + f for f in failure_modes) + """

RULES:
1. Use method introspection -- do NOT hardcode method names.
2. Write EXACTLY 8 tests. No more.
3. No async, no setTimeout, no Promises.
4. Keep tests short (2-4 lines each).
5. Output ONLY valid JavaScript. No markdown. No explanation.

USE THIS EXACT STRUCTURE:

const classes = require('./solution.js');
const Cls = classes[Object.keys(classes)[0]];
let passed = 0; let failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  [PASS] ${name}`); passed++; }
  catch(e) { console.log(`  [FAIL] ${name}: ${e.message}`); failed++; }
}
function assert(c, m) { if (!c) throw new Error(m || 'failed'); }

const _i = new Cls();
const _p = Object.getOwnPropertyNames(Object.getPrototypeOf(_i))
  .filter(m => m !== 'constructor' && typeof _i[m] === 'function');
const addFn    = _p.find(m => /add|push|insert|put|enqueue/i.test(m));
const removeFn = _p.find(m => /remove|delete|del|dequeue|pop/i.test(m));
const getFn    = _p.find(m => /get|fetch|find|peek|next/i.test(m));
const clearFn  = _p.find(m => /clear|reset|empty|flush/i.test(m));
const sizeFn   = _p.find(m => /size|length|count|total/i.test(m));

test('class instantiates', () => {
  const o = new Cls(); assert(o !== null, 'Should instantiate');
});
test('has a main method', () => {
  assert(addFn || getFn, 'Should have at least one main method');
});
// Write 6 more tests (tests 3-8) using the discovered methods above

console.log(`\nResults: ${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);"""

    return _call_llm(prompt, model=model, max_tokens=2000, temperature=0.2)
