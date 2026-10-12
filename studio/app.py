"""HTTP API of Stem Studio, and the built web app.

    GET  /api/health                         liveness
    GET  /api/config                         models and whether a key is set (never the key)
    GET  /api/environments                   what each environment offers, and its tasks
    GET  /api/runs                           runs with their score history
    GET  /api/runs/{name}                    one run: generations, notes, best genome
    GET  /api/runs/{name}/genome?generation= the best genome, or one generation's candidate
    GET  /api/runs/{name}/generations/{g}    task outcomes of a scored generation
    GET  /api/runs/{name}/lineage            accepted changes (git log of the genome)
    GET  /api/runs/{name}/lineage/{sha}      the patch of one change
    GET  /api/eval                           genomes x environments matrix, if one was computed
    POST /api/jobs                           start grow / selftest / check / baseline / matrix
    GET  /api/jobs, /api/jobs/{id}           status and output
    GET  /api/jobs/{id}/events?since=N       output as server-sent events, live
    POST /api/jobs/{id}/stop                 like Ctrl+C: progress is saved, --resume continues
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from stem.config import Settings
from stem.envs import REGISTRY

from . import runs as R
from .jobs import Busy, JobManager

REPO = Path(__file__).resolve().parent.parent
WEB_DIST = REPO / "web" / "dist"

EnvName = Literal[tuple(REGISTRY)]  # type: ignore[valid-type]


class JobRequest(BaseModel):
    kind: Literal["grow", "selftest", "check", "baseline", "matrix"]
    env: EnvName | None = None                          # grow
    run: str | None = Field(None, pattern=R.RUN_NAME.pattern)   # grow: run folder (default: env name)
    generations: int = Field(3, ge=1, le=20)
    dev_steps: int = Field(16, ge=4, le=40)
    trials: int = Field(1, ge=0, le=5)
    train_tasks: int | None = Field(None, ge=1, le=10)
    resume: bool = False
    envs: list[EnvName] = Field(default_factory=list)   # baseline, matrix (empty = all)
    runs: list[str] = Field(default_factory=list)       # matrix: grown runs to compare
    split: Literal["train", "test"] = "test"

    @model_validator(mode="after")
    def _check(self) -> "JobRequest":
        if self.kind == "grow" and not self.env:
            raise ValueError("grow needs an environment")
        if self.kind == "matrix" and not self.runs:
            raise ValueError("matrix needs at least one grown run")
        return self


def create_app(settings: Settings | None = None, repo: Path = REPO, jobs: JobManager | None = None,
               web_dist: Path | None = WEB_DIST) -> FastAPI:
    settings = settings or Settings.from_env(str(repo / ".env"))
    runs_dir = settings.runs_dir if settings.runs_dir.is_absolute() else repo / settings.runs_dir
    jobs = jobs or JobManager(repo)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        jobs.shutdown()  # a run still going when the studio stops is interrupted and stays resumable

    app = FastAPI(title="Stem Studio", version="1.0", docs_url="/api/docs", openapi_url="/api/openapi.json",
                  lifespan=lifespan)
    app.state.jobs = jobs
    app.state.runs_dir = runs_dir
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.exception_handler(R.NotFound)
    async def not_found(_req: Request, exc: R.NotFound):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    # -- read-only -------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/config")
    def config():
        host = settings.api_base.split("//", 1)[-1].split("/", 1)[0]
        return {"api_host": host, "api_key_set": bool(settings.api_key),
                "models": {"develop": settings.model_develop, "act": settings.model_act,
                           "fast": settings.model_fast, "develop_fallback": settings.model_develop_fallback},
                "token_budget": settings.token_budget, "runs_dir": str(runs_dir)}

    @app.get("/api/environments")
    def environments():
        out = []
        for name, cls in REGISTRY.items():
            env = cls()
            out.append({
                "name": name, "brief": env.brief, "max_steps": env.max_steps,
                "actions": [{"name": a.name, "description": a.doc(),
                             "parameters": list(a.parameters.get("properties", {}))} for a in env.actions()],
                "tasks": [{"id": t.id, "split": t.split, "instruction": t.instruction}
                          for split in ("train", "test") for t in env.tasks(split)],
            })
        return out

    @app.get("/api/runs")
    def list_runs():
        return R.list_runs(runs_dir, jobs.active_runs())

    @app.get("/api/runs/{name}")
    def run_detail(name: str):
        path = R.run_dir(runs_dir, name)
        summary = R.summarize(path, name in jobs.active_runs())
        try:
            genome = R.genome_view(R.genome_for(path))
        except R.NotFound:
            genome = None
        candidates = sorted(int(p.name[1:]) for p in (path / "candidates").glob("g[0-9][0-9][0-9]")
                            if (p / "genome.json").is_file())
        return {**summary, "history": R.generations(path), "notebook": R.notebook(path),
                "genome": genome, "candidates": candidates}

    @app.get("/api/runs/{name}/genome")
    def run_genome(name: str, generation: int | None = Query(None, ge=1, le=999)):
        return R.genome_view(R.genome_for(R.run_dir(runs_dir, name), generation))

    @app.get("/api/runs/{name}/generations/{generation}")
    def run_outcomes(name: str, generation: int):
        if not 0 <= generation <= 999:
            raise R.NotFound("no such generation")
        return R.outcomes(R.run_dir(runs_dir, name), generation)

    @app.get("/api/runs/{name}/lineage")
    def run_lineage(name: str):
        return R.lineage(R.genome_for(R.run_dir(runs_dir, name)))

    @app.get("/api/runs/{name}/lineage/{sha}")
    def run_commit(name: str, sha: str):
        return {"sha": sha, "diff": R.commit_diff(R.genome_for(R.run_dir(runs_dir, name)), sha)}

    @app.get("/api/eval")
    def evaluation():
        return R.eval_matrix(runs_dir)

    # -- jobs --------------------------------------------------------------------
    def command_args(req: JobRequest) -> tuple[list[str], str | None]:
        rel = lambda p: str(p.relative_to(repo)) if p.is_relative_to(repo) else str(p)  # noqa: E731
        if req.kind in ("selftest", "check"):
            return [req.kind], None
        if req.kind == "grow":
            name = req.run or req.env
            target = runs_dir / name
            if req.resume and not (target / "run.json").is_file():
                raise HTTPException(400, f"nothing to resume: run {name!r} does not exist")
            args = ["grow", "--env", req.env, "--run", rel(target), "--generations", str(req.generations),
                    "--dev-steps", str(req.dev_steps), "--trials", str(req.trials)]
            if req.train_tasks:
                args += ["--train-tasks", str(req.train_tasks)]
            if req.resume:
                args.append("--resume")
            return args, name
        out = ["--out", rel(runs_dir / "eval"), "--split", req.split]
        envs = [a for e in req.envs for a in ("--env", e)]
        if req.kind == "baseline":
            return ["baseline", *envs, *out], None
        run_args = []
        for name in req.runs:
            run_args += ["--run", rel(R.run_dir(runs_dir, name))]
        return ["matrix", *run_args, *envs, *out], None

    @app.post("/api/jobs", status_code=201)
    def start_job(req: JobRequest):
        try:
            args, run = command_args(req)
        except R.NotFound as e:
            raise HTTPException(400, str(e)) from e
        try:
            return jobs.start(req.kind, args, run).view()
        except Busy as e:
            raise HTTPException(409, str(e)) from e

    @app.get("/api/jobs")
    def list_jobs():
        return [j.view() for j in jobs.list()]

    def job_or_404(job_id: str):
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(404, "no such job")
        return job

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        return job_or_404(job_id).view(with_lines=True)

    @app.post("/api/jobs/{job_id}/stop")
    def stop_job(job_id: str):
        job_or_404(job_id)
        return jobs.stop(job_id).view()

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str, request: Request, since: int = Query(0, ge=0)):
        job = job_or_404(job_id)

        async def stream():
            index = since
            yield "retry: 2000\n\n"
            while True:
                lines, index_next = jobs.lines_since(job, index)
                for offset, text in enumerate(lines):
                    yield f"event: line\ndata: {json.dumps({'i': index_next - len(lines) + offset, 'text': text})}\n\n"
                index = index_next
                if job.status != "running":
                    yield f"event: end\ndata: {json.dumps(job.view())}\n\n"
                    return
                if await request.is_disconnected():
                    return
                await asyncio.sleep(0.3)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # -- the web app -----------------------------------------------------------
    if web_dist and (web_dist / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "not found")
            file = (web_dist / path).resolve()
            if path and file.is_file() and file.is_relative_to(web_dist.resolve()):
                return FileResponse(file)
            return FileResponse(web_dist / "index.html")

    return app
