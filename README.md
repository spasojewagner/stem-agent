# Stem Agent

An agent that starts with no purpose and grows into whatever the environment it is placed in requires. The same code becomes a trader on a simulated exchange, a security reviewer of Python repositories, or a researcher answering questions from a news archive. What it becomes depends only on where you point it.

Its only built-in capability is development: looking at its situation and rewriting its own genome. The genome holds its identity, working instructions, behaviour settings, and the tools, procedures, specialists and hooks it writes for itself. Each accepted change is a git commit, so you can read how it differentiated.

> v1 (the JetBrains internship submission) is kept in [`v1/`](v1) and tagged `v1-jetbrains-submission`. It started as a JavaScript engineer and only tuned its prompt. [DESIGN.md](DESIGN.md) explains what changed and why.

## How it works

```
stem genome (empty)
   │
   ▼
development ──► rewrites a copy of the genome: identity, prompt, mode,
   ▲            tools (Python), skills, sub-agents, hooks
   │                 │
   │                 ▼
   │            copy is scored on training tasks
   │                 │
   └── kept only if it beats the best genome so far
```

- **Environments** (`stem/envs/`) are places, not lessons: a short description, raw actions, tasks and a grader. Each has training tasks and held-out tasks the development process never sees.
- **The core** (`stem/`) contains no domain knowledge. `tests/test_core_is_domain_free.py` fails if it ever does.
- **Tools the agent writes** run in a separate process. They can call environment actions in bulk (`env.<action>(...)`) but cannot open files outside a scratch folder, start processes, use the network or see the API key.
- **Evaluation** is a matrix of genomes by environments on held-out tasks. The undifferentiated stem should score near zero everywhere, each grown genome should score well in its own environment, and stay poor in the others.

## Quick start (Windows, CMD, Python 3.10+)

```
git checkout v2
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
notepad .env                      (paste your Groq key: https://console.groq.com/keys)

python -m stem selftest           offline, no API calls
python -m stem check              key, models and tool calling
python -m stem baseline --env archive
python -m stem grow --env archive --generations 3
python -m stem show --run runs/archive
```

## Running in Docker (recommended for real runs)

The agent writes and executes its own code. The process sandbox stops accidents; the container is the actual boundary.

```
docker compose build
docker compose run --rm stem selftest
docker compose run --rm stem grow --env archive
```

## Commands

| command | what it does |
|---|---|
| `selftest` | Runs every task twice without a model: doing nothing (should score 0) and a reference tool (should score well). Checks the sandbox and the graders. |
| `check` | Makes one small tool-calling request to each configured model. |
| `envs` | Lists environments and tasks. |
| `baseline --env X` | The undifferentiated stem on held-out tasks. |
| `grow --env X [--generations N] [--resume]` | Develops a genome in one environment. Writes to `runs/X/`. |
| `matrix --run runs/a --run runs/b ...` | Grown genomes and the stem across environments, held-out tasks. Writes `runs/eval/matrix.md`. |
| `show --run runs/X [--code]` | The grown genome, its lineage and per-generation scores. |

## Free tier

Groq's free plan limits each model to roughly 8K tokens per minute and 200K tokens per day. The client paces itself from the rate-limit headers and waits on HTTP 429, so runs are slow rather than failing. When a daily limit is hit, the run stops and saves its progress; run the same command again (with `--resume` for `grow`) after the reset at midnight UTC. `STEM_TOKEN_BUDGET` caps one command. Start with one environment, and for a first smoke test use `grow --env archive --generations 1 --train-tasks 1`.

## Layout

```
stem/
  loop.py        agent loop: steps, finish, verification hook, context compaction
  llm.py         OpenAI-compatible client: pacing, retries, budget, quota stop
  genome.py      the genome as a folder with git history
  sandbox.py     runs genome-authored code in a separate process
  phenotype.py   genome + environment -> an agent doing one task
  develop.py     the developmental process (the stem's built-in capability)
  evolve.py      generations and selection
  evaluate.py    genome x environment matrix on held-out tasks
  envs/          exchange, codeaudit, archive (the only domain-aware code)
tests/           pytest suite with a scripted model, and reference tools for selftest
v1/              the original submission
```

## Tests

```
python -m pytest
```
