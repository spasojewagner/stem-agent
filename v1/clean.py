"""
clean.py -- reset the stem agent to a clean state.

Removes accumulated artifacts from previous runs:
  - output/         (timestamped run folders)
  - results/        (baseline.json, evolution_log.json, final_genome.json)
  - state/          (best_agent.json, current_agent.json — learned strategies)
  - benchmarks/tasks/task_interactive/    (dynamically created interactive task)
  - benchmarks/tasks/task_<scenario>/     (dynamically created scenario tasks)
  - __pycache__/    (Python bytecode caches)

KEEPS:
  - source code (*.py)
  - the static benchmark tasks (task_codegen, task_lrucache, task_promisepool)
  - configuration (.env, .env.example, requirements.txt)
  - documentation (*.md)

Usage:
    python clean.py            # preview what would be deleted, ask to confirm
    python clean.py --yes      # skip the confirmation prompt
    python clean.py --soft     # keep state/ and results/, only clear output/ and caches
    python clean.py --help

NOTE: This is for housekeeping. The agent already starts from an EMPTY genome
on every run (see DEFAULT_GENOME in genome.py) — `state/best_agent.json` from
a previous run does NOT carry over. Cleaning is mainly to keep the project
folder tidy and to make sure a fresh `python main.py` produces an output
folder that isn't surrounded by old runs.
"""

import argparse
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# Static benchmark tasks that must NEVER be deleted -- these are the curated
# spec.txt + tests.js + metadata.json triples that ship with the project.
STATIC_BENCHMARK_TASKS = {"task_codegen", "task_lrucache", "task_promisepool"}


def find_targets(soft: bool) -> list:
    """
    Returns a list of (path, kind) tuples to delete.
    kind is one of: "dir", "file".
    """
    targets = []

    # Always clean output/ and __pycache__ dirs
    output_dir = os.path.join(ROOT, "output")
    if os.path.isdir(output_dir):
        for name in sorted(os.listdir(output_dir)):
            p = os.path.join(output_dir, name)
            if os.path.isdir(p):
                targets.append((p, "dir"))

    # Recursively find __pycache__ folders
    for dirpath, dirnames, _ in os.walk(ROOT):
        for d in dirnames:
            if d == "__pycache__":
                targets.append((os.path.join(dirpath, d), "dir"))

    # Dynamically created task folders inside benchmarks/tasks/
    tasks_dir = os.path.join(ROOT, "benchmarks", "tasks")
    if os.path.isdir(tasks_dir):
        for name in sorted(os.listdir(tasks_dir)):
            if name in STATIC_BENCHMARK_TASKS:
                continue
            p = os.path.join(tasks_dir, name)
            if os.path.isdir(p):
                targets.append((p, "dir"))

    if not soft:
        # Also clean state/ and results/ JSONs (the "learned strategies")
        for sub in ("state", "results"):
            d = os.path.join(ROOT, sub)
            if os.path.isdir(d):
                for name in sorted(os.listdir(d)):
                    if name.endswith(".json"):
                        targets.append((os.path.join(d, name), "file"))

    return targets


def human(path: str) -> str:
    """Shorter path display, relative to project root."""
    try:
        return os.path.relpath(path, ROOT)
    except ValueError:
        return path


def main():
    parser = argparse.ArgumentParser(description="Clean the stem agent workspace.")
    parser.add_argument("--yes",  action="store_true", help="Skip the confirmation prompt.")
    parser.add_argument("--soft", action="store_true",
                        help="Soft clean: keep state/ and results/ (learned strategies), only clear output/ and caches.")
    args = parser.parse_args()

    targets = find_targets(soft=args.soft)

    if not targets:
        print("Nothing to clean. Workspace is already tidy.")
        return 0

    mode = "SOFT" if args.soft else "FULL"
    print(f"\nClean mode: {mode}")
    print(f"Items to delete ({len(targets)}):\n")
    for path, kind in targets:
        marker = "DIR " if kind == "dir" else "FILE"
        print(f"  [{marker}]  {human(path)}")

    if args.soft:
        print(f"\nSoft clean keeps: state/, results/ JSONs (the 'learned strategies').")
    else:
        print(f"\nFull clean also removes: state/*.json, results/*.json")
        print(f"(Note: agent already starts from empty genome on every run --")
        print(f" cleaning state/ is for housekeeping, not for resetting behavior.)")

    print(f"\nWill NOT touch: source code, static benchmark tasks "
          f"({', '.join(sorted(STATIC_BENCHMARK_TASKS))}),")
    print(f"                .env, requirements.txt, *.md files.\n")

    if not args.yes:
        try:
            answer = input("Proceed? [y/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return 1
        if answer not in ("y", "yes"):
            print("Aborted.")
            return 1

    deleted = 0
    failed  = 0
    for path, kind in targets:
        try:
            if kind == "dir":
                shutil.rmtree(path)
            else:
                os.remove(path)
            deleted += 1
        except Exception as e:
            print(f"  [ERROR] could not delete {human(path)}: {e}")
            failed += 1

    print(f"\nDone. {deleted} item(s) deleted, {failed} failure(s).")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
