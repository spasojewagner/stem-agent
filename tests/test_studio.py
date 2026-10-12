"""Stem Studio API: reading runs, starting and stopping jobs, serving the UI.

Runs come from studio.demo, which drives the real pipeline with a scripted
model, so these tests need no API key and no network."""
import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stem.config import Settings
from studio import demo
from studio.app import create_app
from studio.jobs import JobManager

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def runs_dir(tmp_path_factory):
    path = tmp_path_factory.mktemp("runs")
    demo.build(path, log=lambda _m: None)
    return path


def client_for(runs_dir, jobs=None, web_dist=None, api_key="sk-secret-value-123"):
    settings = Settings(api_key=api_key, web=False, runs_dir=runs_dir)
    return TestClient(create_app(settings, repo=ROOT, jobs=jobs, web_dist=web_dist))


@pytest.fixture
def api(runs_dir):
    return client_for(runs_dir)


def fake_jobs(script: str) -> JobManager:
    """Jobs that run a small Python script instead of the stem command line."""
    return JobManager(ROOT, command=lambda args: [sys.executable, "-u", "-c", script, *args])


# -- reading -------------------------------------------------------------------
def test_config_says_whether_a_key_is_set_but_never_shows_it(api):
    res = api.get("/api/config")
    assert res.status_code == 200 and res.json()["api_key_set"] is True
    assert "sk-secret-value-123" not in res.text


def test_environments_list_actions_and_held_out_tasks(api):
    envs = {e["name"]: e for e in api.get("/api/environments").json()}
    assert set(envs) == {"exchange", "codeaudit", "archive"}
    splits = {t["split"] for t in envs["archive"]["tasks"]}
    assert splits == {"train", "test"}
    assert envs["archive"]["actions"] and envs["archive"]["brief"]


def test_runs_list_scores_and_kept_generations(api):
    runs = {r["name"]: r for r in api.get("/api/runs").json()}
    assert set(runs) == {"demo-exchange", "demo-archive"}            # eval/ is not a run
    ex = runs["demo-exchange"]
    assert ex["environment"] == "exchange" and ex["generations"] == 4
    assert ex["baseline_score"] == 0.0 and ex["best_score"] > 0.5
    assert [s["accepted"] for s in ex["scores"]] == [True, True, True, False]
    assert ex["kept"] == 2 and ex["tokens"] > 0 and ex["active"] is False


def test_run_detail_has_the_grown_genome_and_notes(api):
    run = api.get("/api/runs/demo-exchange").json()
    assert [t["name"] for t in run["genome"]["tools"]] == ["run_session"]
    assert "def run(env" in run["genome"]["tools"][0]["code"]
    assert run["genome"]["skills"][0]["name"] == "session" and not run["genome"]["is_stem"]
    assert run["notebook"][0]["generation"] == 1 and "status()" in run["notebook"][0]["text"]
    assert run["candidates"] == [1, 2, 3]


def test_a_discarded_candidate_can_be_inspected_and_did_not_replace_the_best(api):
    best = api.get("/api/runs/demo-exchange/genome").json()
    discarded = api.get("/api/runs/demo-exchange/genome", params={"generation": 3}).json()
    assert discarded["mode"]["temperature"] == 0.6
    assert best["mode"]["temperature"] == 0.2
    assert api.get("/api/runs/demo-exchange/genome", params={"generation": 9}).status_code == 404


def test_lineage_lists_accepted_changes_with_their_patches(api):
    commits = api.get("/api/runs/demo-exchange/lineage").json()
    assert [c["subject"].split(":")[0] for c in commits] == ["stem", "g1", "g2"]
    g2 = commits[-1]
    assert "tools/run_session.py" in [f["path"] for f in g2["files"]]
    diff = api.get(f"/api/runs/demo-exchange/lineage/{g2['sha']}").json()["diff"]
    assert "+def run(env" in diff


def test_task_outcomes_of_a_generation(api):
    outs = api.get("/api/runs/demo-exchange/generations/2").json()
    assert outs and all({"task", "score", "digest"} <= set(o) for o in outs)
    assert api.get("/api/runs/demo-exchange/generations/77").status_code == 404


@pytest.mark.parametrize("path", ["/api/runs/..", "/api/runs/%2e%2e", "/api/runs/eval",
                                  "/api/runs/demo-exchange/lineage/not-a-sha",
                                  "/api/runs/demo-exchange/lineage/0123456789abcdef",
                                  "/api/runs/..%2F..%2Fetc/genome"])
def test_requests_cannot_leave_the_runs_folder(api, path):
    assert api.get(path).status_code == 404


def test_evaluation_matrix(api):
    m = api.get("/api/eval").json()
    assert m["split"] == "test"
    assert m["table"]["stem (undifferentiated)"]["exchange"] == 0.0
    assert m["table"]["grown in archive"]["archive"] > m["table"]["grown in archive"]["exchange"]


# -- jobs ----------------------------------------------------------------------
def test_selftest_job_streams_its_output_and_succeeds(runs_dir):
    api = client_for(runs_dir)
    job = api.post("/api/jobs", json={"kind": "selftest"}).json()
    assert job["status"] == "running" and job["command"] == "python -m stem selftest"
    assert api.post("/api/jobs", json={"kind": "selftest"}).status_code == 409   # one at a time

    events, end = [], None
    with api.stream("GET", f"/api/jobs/{job['id']}/events") as res:
        kind = None
        for line in res.iter_lines():
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                if kind == "line":
                    events.append(data)
                elif kind == "end":
                    end = data
    assert end["status"] == "succeeded" and end["exit_code"] == 0
    assert [e["i"] for e in events] == list(range(len(events)))
    assert "selftest passed" in events[-1]["text"]

    again = api.get(f"/api/jobs/{job['id']}/events", params={"since": len(events) - 1})
    assert again.text.count("event: line") == 1


def test_grow_request_becomes_the_command_line(runs_dir):
    jobs = fake_jobs("import sys; print(' '.join(sys.argv[1:]))")
    api = client_for(runs_dir, jobs=jobs)
    job = api.post("/api/jobs", json={"kind": "grow", "env": "exchange", "run": "demo-exchange",
                                      "generations": 2, "dev_steps": 10, "trials": 0,
                                      "train_tasks": 1, "resume": True}).json()
    done = jobs.wait(job["id"], timeout=20)
    assert done.status == "succeeded"
    assert done.lines[0] == (f"grow --env exchange --run {runs_dir / 'demo-exchange'} --generations 2 "
                             f"--dev-steps 10 --trials 0 --train-tasks 1 --resume")
    assert done.run == "demo-exchange"


@pytest.mark.parametrize("body,status", [
    ({"kind": "grow"}, 422),                                         # no environment
    ({"kind": "grow", "env": "moon"}, 422),
    ({"kind": "grow", "env": "archive", "run": "../outside"}, 422),
    ({"kind": "grow", "env": "archive", "generations": 500}, 422),
    ({"kind": "grow", "env": "archive", "run": "never-ran", "resume": True}, 400),
    ({"kind": "matrix", "runs": []}, 422),
    ({"kind": "matrix", "runs": ["missing"]}, 400),
    ({"kind": "shell", "args": ["rm"]}, 422),
])
def test_invalid_job_requests_are_refused(runs_dir, body, status):
    api = client_for(runs_dir, jobs=fake_jobs("print('should not run')"))
    assert api.post("/api/jobs", json=body).status_code == status


def test_stop_interrupts_like_ctrl_c(runs_dir):
    script = ("import time\nprint('working', flush=True)\n"
              "try:\n    time.sleep(60)\nexcept KeyboardInterrupt:\n    print('saved, resumable', flush=True)\n"
              "    raise SystemExit(130)\n")
    jobs = fake_jobs(script)
    api = client_for(runs_dir, jobs=jobs)
    job = api.post("/api/jobs", json={"kind": "check"}).json()
    deadline = time.time() + 10
    while not jobs.get(job["id"]).lines and time.time() < deadline:
        time.sleep(0.05)
    assert api.post(f"/api/jobs/{job['id']}/stop").status_code == 200
    done = jobs.wait(job["id"], timeout=20)
    assert done.status == "stopped" and done.exit_code == 130
    assert done.lines[-1] == "saved, resumable"
    assert api.get("/api/jobs").json()[0]["status"] == "stopped"


def test_running_job_marks_its_run_active(runs_dir):
    jobs = fake_jobs("import time; time.sleep(5)")
    api = client_for(runs_dir, jobs=jobs)
    job = api.post("/api/jobs", json={"kind": "grow", "env": "archive", "run": "demo-archive",
                                      "resume": True}).json()
    runs = {r["name"]: r["active"] for r in api.get("/api/runs").json()}
    assert runs == {"demo-archive": True, "demo-exchange": False}
    jobs.stop(job["id"])
    jobs.wait(job["id"], timeout=20)


# -- the web app ---------------------------------------------------------------
def test_built_ui_is_served_with_client_side_routes(runs_dir, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>studio</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("outside")
    api = client_for(runs_dir, web_dist=dist)
    assert api.get("/").text == "<html>studio</html>"
    assert api.get("/runs/demo-exchange").text == "<html>studio</html>"     # React Router path
    assert api.get("/assets/app.js").text == "console.log(1)"
    assert "outside" not in api.get("/..%2Fsecret.txt").text
    assert api.get("/api/nothing-here").status_code == 404
