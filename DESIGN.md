# Design

## What went wrong in v1

v1's agent was "a JavaScript engineer that implements classes from specifications" from its first line. Evolution appended strategies to that prompt and switched pre-written tools on and off. The benchmark (an LRU cache, a promise pool) is something a model solves without any evolution, so the starting score was already high. That is a specialised agent with a learning loop, not a stem agent, and the improvement it measured was prompt tuning on a fixed problem.

v2 starts from the opposite end and checks each point in code, not in prose.

## Decisions

**What "not specialised" means for the starting state.** The stem genome is empty: no identity, no instructions, no tools, no procedures. The core code contains no domain knowledge, and a test fails if a domain word appears in it. At task time the stem has only the environment's raw actions and the step limit. That is deliberately not enough. Every environment is built so that doing nothing scores 0 and the raw actions alone can't cover the task within the step budget.

**Development versus function.** A cell differentiates and then works. Here the genome can only change during development, never while a task is being done. This keeps evaluation honest: a held-out score measures what the agent became, not what it improvised on the spot.

**Who picks the frame.** Development is told where the agent is (the environment's description, its actions, the training tasks) and that held-out tasks of the same kind decide the outcome. It is not told what to become. It writes the identity itself, decides which capabilities to build, and can probe the environment and search the web before committing. The same developmental code and the same prompt run in every environment.

**What can evolve.** Model tier, behaviour mode (step budget, temperature, planning, periodic reflection), identity, working instructions, tools written as Python, written procedures, sub-agents with their own instructions and tool subsets, and two hooks: one that prepares context at the start of a task and one that can reject an answer before it is submitted. Tools can call environment actions many times per agent step. That is where most real specialisation shows up: a trading policy that runs a whole session, a repository scanner, an archive indexer.

**Selection.** A developed copy is scored on all training tasks and kept only if it beats the best so far. One exception: while nothing has scored above zero, any change is kept, so groundwork such as a half-finished tool isn't thrown away. Discarded attempts and their scores are shown to the next generation.

**Evaluation that tests the evolution itself.** The main result is a matrix of genomes (stem, plus one grown in each environment) by environments, on held-out tasks:

- the stem row should be near zero everywhere (a baseline above ~0.4 would mean the task doesn't need specialisation),
- the diagonal should be high,
- off-diagonal cells should stay low. A genome grown into a trader should be a poor security reviewer. Otherwise nothing differentiated, and we only measured a generally better prompt.

**The tasks are agentic.** Every task needs many tool calls, decisions about what to look at next, and a decision about when to stop. Grading uses only what the agent did and answered.

| environment | the agent must | held-out tasks differ by |
|---|---|---|
| exchange | grow equity over a 160-180 period session; graded against holding cash or buying and holding, and against the best of a set of simple strategies run on the same prices | new symbols, a regime switch mid-session, a different volatility |
| codeaudit | find planted vulnerabilities in ~90 generated files and file findings; graded by F1 | half of the vulnerable idioms never appear in training repositories |
| archive | answer one aggregation question from ~95 documents, with corrections, cancelled deals and renamed companies; exact grading | new question types and phrasings that never appear in training archives |

`python -m stem selftest` shows, for every task, that doing nothing scores 0 and that a reference tool working through the same sandbox scores well. A scanner or extractor built only from training patterns loses points on held-out tasks (see `tests/test_envs.py`), so generalisation is part of the measurement.

**Web access** is given to development only: server-side search through the provider, and fetching from an allow-list of domains. Genome-authored code gets no network.

**Security.** Genome-authored code runs in a separate Python process with a stripped environment (no API key), a timeout, CPU and memory limits on Linux, a cap on environment calls, and soft barriers: no sockets, no subprocesses, no directory listing, file access only inside a scratch folder, imports only from the standard library. These stop accidents and shortcuts such as reading an environment's source from disk. They do not stop a determined attacker running as the same user, which is why the Docker setup exists (read-only filesystem, no capabilities, memory and process limits).

**Models.** Defaults target Groq's free tier: `openai/gpt-oss-120b` for development, `llama-3.3-70b-versatile` for doing tasks, `llama-3.1-8b-instant` for sub-agents, `openai/gpt-oss-20b` for web search. Each model has its own daily quota, so the load is spread across them. Any OpenAI-compatible endpoint can be configured.

## Known limitations

- The environments are synthetic. That keeps them reproducible and offline, but they are smaller than real ones.
- Three tasks per split is enough to see differentiation, not to make fine statistical claims.
- Selection is greedy with one lineage per environment. A population would explore more but costs proportionally more quota.
- Development quality depends heavily on the model. On the free tier, per-minute token limits make runs slow.
