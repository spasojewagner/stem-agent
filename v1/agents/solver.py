"""
Solver -- calls the LLM with the current genome's system prompt.
temperature=0 for deterministic, reproducible results.

If enabled_tools is non-empty, pre_solve tools run first to augment the
user message, and post_solve tools run on the resulting code (may revise it
or inject method aliases). With no tools the behavior is identical to the
pre-tools project.
"""
import os
import requests


def solve_task(task: dict, system_prompt: str, enabled_tools: list = None) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set.")

    spec = task.get("spec", task.get("question", "Solve the task as described."))
    enabled_tools = enabled_tools or []

    # --- Pre-solve tools (if any)
    if enabled_tools:
        from agents.tools import run_pre_solve_tools, build_augmented_user_message
        tool_context = run_pre_solve_tools(enabled_tools, {"spec": spec})
        user_message = build_augmented_user_message(spec, tool_context)
    else:
        user_message = (
            f"Task specification:\n\n{spec}\n\n"
            "Respond with ONLY the implementation code in a code block. No explanation."
        )

    # --- Main solver call
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "max_tokens": 1500,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message}
            ]
        },
        timeout=30
    )

    if response.status_code != 200:
        raise Exception(f"API error {response.status_code}: {response.text[:200]}")

    raw_response = response.json()["choices"][0]["message"]["content"]

    # --- Post-solve tools (if any)
    if not enabled_tools:
        return raw_response

    # Extract code so post-solve tools can operate on it
    from executor import extract_code
    from agents.tools import run_post_solve_tools

    code = extract_code(raw_response)
    post_context = run_post_solve_tools(
        enabled_tools,
        {"spec": spec, "code": code}
    )
    revised_code = post_context.get("code", code)

    # Return as a code block so the executor's extractor finds it the same way
    return f"```javascript\n{revised_code}\n```"
