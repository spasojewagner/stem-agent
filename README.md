# Stem Agent

Author: Marko Spasojevic

A console-based agent that specializes into JavaScript code generation
from vague specifications. Starts with zero strategies and grows into a
specialist through evolution.

## Requirements

- Python 3.9+
- Node.js (for running JavaScript tests)
- OpenAI API key
- 
## Clone projeCT

```bash
git clone https://github.com/spasojewagner/stem-agent.git
cd stem-agent/stem-agent-metoda

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and replace the placeholder with your OpenAI API key.

## Usage

Interactive mode (the system asks you to type a prompt):

```bash
python main.py
```

Direct prompt:

```bash
python main.py --prompt "Build a simple bank account manager"
```

With the optional tool registry (the mutator can also evolve tools, not
only strategies):

```bash
python main.py --prompt "..." --use-tools
```

Other modes:

```bash
python main.py --benchmark               # run the default 3-task benchmark
python main.py --scenario restaurant     # built-in multi-task scenario
python main.py --domain "data structures" # auto-generate 3 tasks in a JS sub-domain
```

## Output

Every run creates a folder under `output/` with the spec, generated tests,
final implementation, scores, and full evolution log.

## Cleanup

```bash
python clean.py            # preview and confirm
python clean.py --yes      # no confirmation
python clean.py --soft     # keep state/ and results/
```

## Project layout

```
main.py              entry point, CLI, scope guard
genome.py            data structure (strategies + tools)
evolve.py            evolution loop
evaluate.py          run a benchmark of tasks
executor.py          run `node tests.js`, parse pass/fail
evaluator.py         generate tests from spec (independent model)
agents/solver.py     agent that writes JavaScript
agents/mutator.py    proposes new strategies / tools
agents/tools.py      optional tool registry
main_scenarios.py    hand-curated scenarios
domain_explorer.py   auto-generate tasks for a JS sub-domain
utils.py             small helpers
clean.py             workspace reset
```
