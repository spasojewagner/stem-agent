import pytest

from stem.genome import Genome, GenomeError


def test_tool_validation(tmp_path):
    g = Genome.stem(tmp_path / "g")
    obj = {"type": "object", "properties": {}}
    with pytest.raises(GenomeError):
        g.write_tool("scan", "d", obj, "def other():\n    pass\n")
    with pytest.raises(GenomeError):
        g.write_tool("scan", "d", obj, "def run(env:\n")
    with pytest.raises(GenomeError):
        g.write_tool("Bad Name", "d", obj, "def run(env):\n    return 1\n")
    g.write_tool("scan", "d", obj, "def run(env):\n    return 1\n")
    assert [t.name for t in g.tools()] == ["scan"] and not g.is_stem()


def test_mode_is_clamped(tmp_path):
    g = Genome.stem(tmp_path / "g")
    mode = g.set_mode(max_steps=500, temperature=3, reflect_every=-2)
    assert mode["max_steps"] == 30 and mode["temperature"] == 1.0 and mode["reflect_every"] == 0
    with pytest.raises(GenomeError):
        g.set_mode(model_tier="gpt-9")


def test_copy_fingerprint_and_lineage(tmp_path):
    g = Genome.stem(tmp_path / "g")
    c = g.copy_to(tmp_path / "c")
    assert c.fingerprint() == g.fingerprint()
    c.set_identity("something")
    c.write_skill("how", "step one")
    assert c.fingerprint() != g.fingerprint()
    c.commit("g1: became something")
    log = c.log()
    if log:  # git is optional
        assert "stem: undifferentiated genome" in log and "g1: became something" in log


def test_changes_since(tmp_path):
    g = Genome.stem(tmp_path / "g")
    c = g.copy_to(tmp_path / "c")
    c.set_identity("x")
    c.write_tool("scan", "d", {"type": "object", "properties": {}}, "def run(env):\n    return 1\n")
    text = c.changes_since(g)
    assert "identity changed" in text and "tools/scan.py added" in text
    assert g.changes_since(g) == "no changes"
