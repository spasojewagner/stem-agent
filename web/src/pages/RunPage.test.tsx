import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Genome, RunDetail } from "../api/types";
import { exchangeRun } from "../test/fixtures";
import { mockApi, renderAt } from "../test/render";
import { RunPage } from "./RunPage";

const genome: Genome = {
  identity: "A disciplined agent that plays the whole session by fixed rules.",
  system_prompt: "Call run_session once, then finish.",
  mode: { max_steps: 12, temperature: 0.2, plan_first: false, reflect_every: 0, model_tier: "act" },
  tools: [{ name: "run_session", description: "Plays the whole session.", parameters: { properties: {} },
    code: "def run(env):\n    return env.status()\n" }],
  skills: [], subagents: [], hooks: [], fingerprint: "3527c9a28f11", is_stem: false,
};

const detail: RunDetail = {
  ...exchangeRun,
  history: exchangeRun.scores.map((s) => ({
    generation: s.generation, accepted: s.accepted, train_score: s.score, per_task: {},
    summary: s.generation === 2 ? "Wrote run_session, which plays the session in one call."
      : s.generation === 3 ? "Raised temperature." : "baseline",
    fingerprint: "x", tokens_used: 41_000, seconds: 95,
  })),
  notebook: [{ generation: 1, text: "status() returns cash and holdings." }],
  genome,
  candidates: [1, 2, 3],
};

function api() {
  return mockApi({
    "GET /api/runs/exchange-1": detail,
    "GET /api/runs/exchange-1/genome": genome,
    "GET /api/runs/exchange-1/genome?generation=3": { ...genome, mode: { ...genome.mode, temperature: 0.6 } },
    "GET /api/runs/exchange-1/generations/3": [],
    "GET /api/runs/exchange-1/generations/2": [
      { task: "ex-train-1", score: 0.88, note: "return +20.6%", stopped: "finished", steps: 2, final: "", digest: "1. run_session({}) -> ..." },
    ],
    "GET /api/runs/exchange-1/lineage": [
      { sha: "aaaaaaa1", short: "aaaaaaa", date: "", subject: "stem: undifferentiated genome", body: "", files: [] },
      { sha: "bbbbbbb2", short: "bbbbbbb", date: "", subject: "g2: training score 0.71", body: "Wrote run_session.",
        files: [{ path: "tools/run_session.py", added: 2, removed: 0 }] },
    ],
    "GET /api/runs/exchange-1/lineage/bbbbbbb2": { sha: "bbbbbbb2",
      diff: "diff --git a/tools/run_session.py b/tools/run_session.py\nnew file mode 100644\n--- /dev/null\n+++ b/tools/run_session.py\n@@ -0,0 +1,2 @@\n+def run(env):\n+    return env.status()\n" },
    "GET /api/jobs": [],
  });
}

describe("RunPage", () => {
  it("opens on the latest generation and switches to another one", async () => {
    api();
    renderAt(<RunPage />, { route: "/runs/exchange-1", path: "/runs/:name" });
    expect(await screen.findByRole("heading", { name: "Generation 3" })).toBeInTheDocument();
    expect(screen.getByText(/Discarded: it did not beat/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Generation 2, kept/ }));
    expect(screen.getByRole("heading", { name: "Generation 2" })).toBeInTheDocument();
    expect(screen.getByText("Wrote run_session, which plays the session in one call.")).toBeInTheDocument();
    expect(await screen.findByText("ex-train-1")).toBeInTheDocument();
  });

  it("shows the grown genome and a discarded candidate", async () => {
    api();
    renderAt(<RunPage />, { route: "/runs/exchange-1", path: "/runs/:name" });
    expect(await screen.findByText(genome.identity)).toBeInTheDocument();
    expect(screen.getByText("tools/run_session.py")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Inspect the genome this generation produced" }));
    expect(await screen.findByText("This candidate was discarded.")).toBeInTheDocument();
    expect(await screen.findByText("0.6")).toBeInTheDocument();
  });

  it("shows each accepted change as a diff, and the notes", async () => {
    api();
    renderAt(<RunPage />, { route: "/runs/exchange-1", path: "/runs/:name" });
    await userEvent.click(await screen.findByRole("tab", { name: "Changes" }));
    const panel = await screen.findByRole("tabpanel");
    expect(await within(panel).findByText("+def run(env):")).toBeInTheDocument();
    expect(within(panel).getByText("Wrote run_session.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "Notes (1)" }));
    expect(screen.getByText("status() returns cash and holdings.")).toBeInTheDocument();
  });

  it("offers to continue the run", async () => {
    api();
    renderAt(<RunPage />, { route: "/runs/exchange-1", path: "/runs/:name" });
    expect(await screen.findByRole("link", { name: "Continue growing" }))
      .toHaveAttribute("href", "/grow?env=exchange&run=exchange-1&resume=1");
  });
});
