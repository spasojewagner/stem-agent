import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { EnvironmentInfo, StudioConfig } from "../api/types";
import { exchangeRun } from "../test/fixtures";
import { mockApi, renderAt } from "../test/render";
import { GrowPage } from "./GrowPage";

const envs: EnvironmentInfo[] = ["exchange", "codeaudit", "archive"].map((name) => ({
  name, brief: `The ${name} environment.`, max_steps: 14, actions: [],
  tasks: [{ id: `${name}-train-1`, split: "train", instruction: "x" }, { id: `${name}-test-1`, split: "test", instruction: "y" }],
}));
const config: StudioConfig = { api_host: "api.groq.com", api_key_set: true, models: { develop: "a", act: "b", fast: "c" },
  token_budget: 400000, runs_dir: "runs" };

function api(extra: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/environments": envs, "GET /api/runs": [exchangeRun], "GET /api/config": config, "GET /api/jobs": [],
    "POST /api/jobs": { id: "job1", kind: "grow", status: "running" }, ...extra,
  });
}

describe("GrowPage", () => {
  it("starts a run with the chosen settings and opens its live output", async () => {
    const calls = api();
    renderAt(<GrowPage />, { route: "/grow" });
    await userEvent.click(await screen.findByText("codeaudit"));
    await userEvent.type(screen.getByLabelText("Run folder"), "audit-try");
    const gens = screen.getByLabelText("Generations");
    await userEvent.clear(gens);
    await userEvent.type(gens, "5");
    await userEvent.click(screen.getByRole("button", { name: "Start growing" }));

    expect(await screen.findByText("job page")).toBeInTheDocument();
    expect(calls.find((c) => c.key === "POST /api/jobs")?.body).toEqual({
      kind: "grow", env: "codeaudit", run: "audit-try", generations: 5, dev_steps: 16, trials: 1,
      train_tasks: null, resume: false,
    });
  });

  it("continues an existing run when opened from its page", async () => {
    const calls = api();
    renderAt(<GrowPage />, { route: "/grow?env=exchange&run=exchange-1&resume=1" });
    expect(await screen.findByRole("heading", { name: "Continue exchange-1" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Continue growing" }));
    await screen.findByText("job page");
    expect(calls.find((c) => c.key === "POST /api/jobs")?.body).toMatchObject(
      { kind: "grow", env: "exchange", run: "exchange-1", resume: true, generations: 1 });
  });

  it("warns before starting an existing run over", async () => {
    api();
    renderAt(<GrowPage />, { route: "/grow" });
    await userEvent.type(await screen.findByLabelText("Run folder"), "exchange-1");
    expect(screen.getByText(/exists and will be started over/)).toBeInTheDocument();
  });

  it("does not start a second job while one runs", async () => {
    api({ "GET /api/jobs": [{ id: "j0", kind: "grow", run: "x", status: "running" }] });
    renderAt(<GrowPage />, { route: "/grow" });
    expect(await screen.findByText(/Another job is running/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start growing" })).toBeDisabled();
  });
});
