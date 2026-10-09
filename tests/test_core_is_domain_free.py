"""The stem must not know what it will become.

v1 failed here: the agent was a JavaScript engineer from its first line.
This test fails the moment the core mentions any domain. Environments
(stem/envs/) and the command line (which wires environments up) are the
only places allowed to.
"""
import re
from pathlib import Path

from stem.envs import REGISTRY
from stem.genome import Genome
from stem.phenotype import UNDIFFERENTIATED, system_prompt

CORE = Path(__file__).resolve().parent.parent / "stem"
ALLOWED = {"__main__.py"}

DOMAIN_WORDS = [
    # environment names
    *REGISTRY.keys(),
    # words that would smuggle a specialisation into the core
    "trade", "trading", "trader", "price", "portfolio", "stock", "market", "finance",
    "vulnerab", "exploit", "injection", "audit", "security",
    "revenue", "acquisition", "company", "companies", "research",
    "javascript", "node.js", "code generation",
]


def core_files():
    for p in CORE.glob("*.py"):
        if p.name not in ALLOWED:
            yield p


def test_core_mentions_no_domain():
    offenders = []
    for path in core_files():
        text = path.read_text(encoding="utf-8").lower()
        for word in DOMAIN_WORDS:
            if re.search(rf"\b{re.escape(word)}", text):
                offenders.append(f"{path.name}: '{word}'")
    assert not offenders, "core is not domain-free:\n" + "\n".join(offenders)


def test_core_does_not_import_environments():
    for path in core_files():
        text = path.read_text(encoding="utf-8")
        assert "from .envs" not in text and "import envs" not in text, path.name


def test_stem_genome_is_empty(tmp_path):
    g = Genome.stem(tmp_path / "g")
    assert g.is_stem()
    assert g.tools() == [] and g.skills() == {} and g.subagents() == {}


def test_stem_phenotype_has_no_purpose(tmp_path):
    g = Genome.stem(tmp_path / "g")
    for cls in REGISTRY.values():
        prompt = system_prompt(g, cls(), 10)
        assert UNDIFFERENTIATED in prompt
        assert "# How you work" not in prompt
