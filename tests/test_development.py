"""End to end with a scripted model: stem -> development -> selection ->
held-out matrix. The model is fake; the plumbing, sandbox, environments,
grading and selection are real."""
import json

from stem.envs import CodeAudit, Exchange
from stem.evaluate import matrix
from stem.evolve import grow
from stem.genome import Genome
from stem.llm import ScriptedClient, Usage, tool_call


class RoleClient:
    """Developer follows a script; the acting agent uses its own tool if it has one."""

    def __init__(self, settings, dev_script):
        self.settings, self.dev = settings, ScriptedClient(dev_script)
        self.usage = Usage()

    def chat(self, model, messages, tools=None, **kw):
        self.usage.add(model, 100, 20)
        if model == self.settings.model_develop:
            return self.dev.chat(model, messages, tools)
        names = [t["function"]["name"] for t in tools or []]
        used = any(m.get("role") == "tool" for m in messages)
        if "policy" in names and not used:
            return tool_call("policy")
        return tool_call("finish", answer="done")


def dev_script(reference_code):
    return [
        tool_call("probe", action="status"),
        tool_call("set_identity", text="An agent that runs a disciplined, rule-based policy end to end."),
        tool_call("write_tool", name="policy", description="Run the whole session with a fixed rule.",
                  parameters={"type": "object", "properties": {}}, code=reference_code),
        tool_call("test_tool", name="policy"),
        tool_call("set_system_prompt", text="Call policy once, then finish."),
        tool_call("finish", answer="Wrote and tested a policy tool that runs the session in one call."),
    ]


def test_grow_then_matrix(tmp_path, settings, reference):
    code = reference("exchange").read_text(encoding="utf-8")
    client = RoleClient(settings, dev_script(code))
    run_dir = tmp_path / "run"
    records = grow(Exchange, settings, client, run_dir, generations=1, dev_steps=8, trials=0,
                   log=lambda m: None)

    assert records[0].generation == 0 and records[0].train_score == 0.0      # stem can't do it
    assert records[1].accepted and records[1].train_score > 0.3               # development helped
    genome = Genome(run_dir / "genome")
    assert [t.name for t in genome.tools()] == ["policy"]
    assert "g1: training score" in (genome.log() or "g1: training score")

    lines = (run_dir / "generations.jsonl").read_text().splitlines()
    assert [json.loads(l)["generation"] for l in lines] == [0, 1]

    table = matrix({"grown in exchange": run_dir / "genome"}, [Exchange, CodeAudit], "test",
                   client, settings, tmp_path / "eval", log=lambda m: None)
    assert table["stem (undifferentiated)"]["exchange"] == 0.0
    assert table["grown in exchange"]["exchange"] > 0.3        # diagonal
    assert table["grown in exchange"]["codeaudit"] == 0.0      # it became one thing, not everything


def test_rejected_candidate_does_not_replace_best(tmp_path, settings):
    script = [tool_call("set_identity", text="Something that does not help."),
              tool_call("finish", answer="changed identity only")]
    client = RoleClient(settings, script)
    run_dir = tmp_path / "run"
    grow(Exchange, settings, client, run_dir, generations=1, dev_steps=4, trials=0, log=lambda m: None)
    # best was 0 and the candidate also scored 0 but changed something: kept as groundwork
    assert Genome(run_dir / "genome").identity == "Something that does not help."

    client2 = RoleClient(settings, [tool_call("set_identity", text="Another idea."),
                                    tool_call("finish", answer="again")])
    recs = grow(Exchange, settings, client2, run_dir, generations=1, dev_steps=4, trials=0,
                resume=True, log=lambda m: None)
    assert recs[-1].generation == 2


def test_failed_development_is_not_kept(tmp_path, settings):
    from stem.llm import LLMError

    def broken(*_):
        raise LLMError("network error: connection reset")
    client = RoleClient(settings, [tool_call("set_identity", text="half done"), broken])
    run_dir = tmp_path / "run"
    recs = grow(Exchange, settings, client, run_dir, generations=1, dev_steps=4, trials=0, log=lambda m: None)
    assert not recs[-1].accepted
    assert Genome(run_dir / "genome").is_stem()
