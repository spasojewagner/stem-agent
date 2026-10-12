"""python -m studio.demo: example runs for trying the studio without an API key.

The runs are produced by the real pipeline (development, sandboxed tools,
environments, grading, selection, held-out matrix). Only the language model
is replaced by a script: the "developer" follows fixed steps that end with
the reference tools from tests/reference/, and the acting agent calls its
own tool when it has one. The runs are named demo-* and their run.json lists
the model as "scripted demo", so they are never mistaken for real results.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from stem.config import Settings
from stem.envs import Archive, CodeAudit, Exchange
from stem.evaluate import matrix
from stem.evolve import grow
from stem.llm import ScriptedClient, Usage, tool_call

REPO = Path(__file__).resolve().parent.parent
OWN_TOOL = "(one of your own tools)"


class DemoClient:
    """Development follows `dev_script`; the acting agent uses its own tool if it has one."""

    def __init__(self, settings: Settings, dev_script: list):
        self.settings = settings
        self.dev = ScriptedClient(dev_script)
        self.usage = Usage()

    def chat(self, model, messages, tools=None, **_kw):
        if model == self.settings.model_develop:
            msg = self.dev.chat(model, messages, tools)
            self.usage.add(model, 1800, 260)
            return msg
        self.usage.add(model, 900, 60)
        own = [t["function"] for t in tools or [] if OWN_TOOL in t["function"].get("description", "")]
        results = [m for m in messages if m.get("role") == "tool"]
        if own and not results:
            args = {}
            if "question" in own[0].get("parameters", {}).get("properties", {}):
                task = messages[1]["content"]
                args["question"] = re.sub(r"^Task:\s*", "", task.split("\n\n")[0])
            return tool_call(own[0]["name"], **args)
        answer = results[-1]["content"] if results else "I have no way to do this yet."
        return tool_call("finish", answer=answer[:400])


def _reference(name: str) -> str:
    return (REPO / "tests" / "reference" / f"{name}_reference.py").read_text(encoding="utf-8")


def exchange_script() -> list:
    return [
        # g1: looks around, keeps notes, sets an identity, writes no tool yet
        tool_call("probe", action="status"),
        tool_call("note", text="status() returns cash, positions and the current tick; orders fill at the next tick."),
        tool_call("set_identity", text="A disciplined agent that runs a whole session on this exchange by fixed rules "
                                       "and is judged on what it ends with."),
        tool_call("finish", answer="Explored status and orders, wrote notes and an identity. No tool yet."),
        # g2: writes the tool that runs the whole session, tests it, writes how to use it
        tool_call("write_tool", name="run_session", description="Run the whole session with a fixed rule set.",
                  parameters={"type": "object", "properties": {}}, code=_reference("exchange")),
        tool_call("test_tool", name="run_session"),
        tool_call("set_system_prompt", text="Call run_session once. It plays the whole session. Then call finish "
                                            "with its report."),
        tool_call("write_skill", name="session", content="1. run_session() once.\n2. finish with its report."),
        tool_call("finish", answer="Wrote and tested run_session, which plays the whole session in one call."),
        # g3: tries a different behaviour that does not improve the score (discarded)
        tool_call("set_mode", temperature=0.6, reflect_every=3),
        tool_call("finish", answer="Raised temperature and added reflection to explore other policies."),
    ]


def archive_script() -> list:
    return [
        tool_call("probe", action="list_documents", args={"page": 1}),
        tool_call("note", text="Documents are paged; facts appear in several phrasings and companies get renamed."),
        tool_call("set_identity", text="A researcher that answers questions from this archive only from what the "
                                       "documents say."),
        tool_call("finish", answer="Read the listing format, noted the phrasing problem, set an identity."),
        tool_call("write_tool", name="answer_question", description="Read every document, extract the facts and "
                  "answer the question.",
                  parameters={"type": "object", "properties": {"question": {"type": "string"}},
                              "required": ["question"]}, code=_reference("archive")),
        tool_call("test_tool", name="answer_question", args={"question": "probe"}),
        tool_call("set_system_prompt", text="Pass the question to answer_question and finish with its answer."),
        tool_call("finish", answer="Wrote answer_question, which crawls the archive and answers from extracted facts."),
    ]


def build(runs_dir: Path, log=print) -> None:
    settings = Settings(api_key="", web=False, tool_timeout=120, runs_dir=runs_dir,
                        model_develop="scripted demo (develop)", model_act="scripted demo (act)",
                        model_fast="scripted demo (fast)")
    quiet = lambda _m: None  # noqa: E731
    grown = {}
    for env_cls, script, gens in ((Exchange, exchange_script(), 3), (Archive, archive_script(), 2)):
        run = runs_dir / f"demo-{env_cls.name}"
        log(f"growing {run.name} ({gens} generations, scripted model) ...")
        records = grow(env_cls, settings, DemoClient(settings, script), run, generations=gens,
                       dev_steps=8, trials=0, train_limit=2, log=quiet)
        for r in records:
            log(f"  g{r.generation}: {'kept' if r.accepted else 'discarded'}, training score {r.train_score:.2f}")
        grown[f"grown in {env_cls.name}"] = run / "genome"
    log("held-out matrix ...")
    table = matrix(grown, [Exchange, CodeAudit, Archive], "test",
                   DemoClient(settings, []), settings, runs_dir / "eval", log=quiet)
    for label, row in table.items():
        log(f"  {label}: " + ", ".join(f"{k} {v:.2f}" for k, v in row.items()))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m studio.demo", description=__doc__.splitlines()[0])
    p.add_argument("--runs", default=str(REPO / "runs"))
    args = p.parse_args(argv)
    build(Path(args.runs))


if __name__ == "__main__":
    main()
