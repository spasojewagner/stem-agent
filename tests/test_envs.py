import pytest

from stem.envs import REGISTRY
from stem.envs.archive import REVENUE_PHRASES, World
from stem.envs.codeaudit import VULNS, build_repo
from stem.envs.exchange import Exchange
from stem.sandbox import run_code

ALL = [(name, split, t) for name, cls in REGISTRY.items() for split in ("train", "test") for t in cls().tasks(split)]


def test_splits_are_disjoint_and_sized():
    for name, cls in REGISTRY.items():
        train = {t.id for t in cls().tasks("train")}
        test = {t.id for t in cls().tasks("test")}
        assert len(train) >= 3 and len(test) >= 3 and not train & test, name


@pytest.mark.parametrize("name,split,task", ALL, ids=[t.id for _, _, t in ALL])
def test_doing_nothing_scores_zero(name, split, task):
    env = REGISTRY[name]()
    env.start(task)
    assert env.score("")[0] == 0.0


@pytest.mark.parametrize("name,split,task", ALL, ids=[t.id for _, _, t in ALL])
def test_solvable_through_a_tool(name, split, task, reference):
    env = REGISTRY[name]()
    env.start(task)
    args = {"question": task.instruction} if name == "archive" else {}
    out, _ = run_code(reference(name), args, env.call, timeout=120, max_env_calls=env.max_internal_calls)
    assert env.score(out)[0] >= 0.4, out[:200]


def test_exchange_has_no_lookahead():
    env = Exchange()
    env.start(env.tasks("train")[0])
    hist = env.prices("ALFA", 200)
    assert len(hist) == env.t + 1 and hist[-1] == env.series["ALFA"][env.t]
    env.advance(5)
    assert env.prices("ALFA", 1)[-1] == env.series["ALFA"][env.t]


def test_heldout_code_uses_unseen_idioms():
    train_lines = {l.replace("  #!", "") for c in VULNS.values() for s in c["train"] for l in s if "#!" in l}
    test_lines = {l.replace("  #!", "") for c in VULNS.values() for s in c["test"] for l in s if "#!" in l}
    for seed in (41, 42, 43):
        files, truth = build_repo(seed, "test")
        planted = {files[p][ln - 1] for p, ln, _ in truth}
        assert planted & test_lines and planted & train_lines


def test_heldout_archives_use_unseen_phrasing():
    def uses_test_phrasing(world):
        stems = [p.split("{")[0] or p.split("}")[1][:12] for p in REVENUE_PHRASES["test"]]
        text = " ".join(d["text"] for d in world.docs)
        return "posted sales of" in text or "with turnover of" in text
    assert not any(uses_test_phrasing(World(s, "train")) for s in (51, 52, 53))
    assert all(uses_test_phrasing(World(s, "test")) for s in (61, 62, 63))


def test_questions_do_not_leak_answers():
    for t in REGISTRY["archive"]().tasks("test"):
        env = REGISTRY["archive"]()
        env.start(t)
        assert str(env.expected) not in t.instruction


def test_training_only_specialisation_loses_points_on_heldout(tmp_path, reference):
    """A scanner that only knows the idioms seen in training must do worse on
    held-out repositories than on training ones: generalisation is measured."""
    src = reference("codeaudit").read_text(encoding="utf-8")
    narrow = src.replace('r"execute\\((f\\"|\\".*(%|\\.format\\()|\\w+\\))"', 'r"execute\\((f\\"|\\".*%)"') \
                .replace('|shell=True|os\\.popen\\(', '|f\\".*shell=True') \
                .replace('|yaml\\.load\\(.*Loader=yaml\\.Loader|jsonpickle\\.decode', '') \
                .replace('(md5|sha1)\\((password|pwd)', 'md5\\(password') \
                .replace('r"\\beval\\(|\\bexec\\("', 'r"eval\\(request"')
    assert narrow != src
    tool = tmp_path / "narrow.py"
    tool.write_text(narrow, encoding="utf-8")
    means = {}
    for split in ("train", "test"):
        scores = []
        for t in REGISTRY["codeaudit"]().tasks(split):
            env = REGISTRY["codeaudit"]()
            env.start(t)
            run_code(tool, {}, env.call, timeout=120, max_env_calls=env.max_internal_calls)
            scores.append(env.score("")[0])
        means[split] = sum(scores) / len(scores)
    assert means["test"] < means["train"] - 0.1, means


def test_every_natural_call_style_works():
    from stem.envs import Archive
    env = Archive()
    env.start(env.tasks("train")[0])
    a = env.call("read", {"doc_id": "D001"})
    b = env.call("read", {"__pos__": ["D001"]})
    c = env.call("read", {"__pos__": [{"doc_id": "D001"}]})
    assert a == b == c
    with pytest.raises(ValueError, match=r"search\(query: string\) is missing"):
        env.call("search", {})
    with pytest.raises(ValueError, match="no parameter"):
        env.call("read", {"id": "D001"})
