import { act, screen } from "@testing-library/react";

import type { Job } from "../api/types";
import { mockApi, renderAt } from "../test/render";
import { JobPage } from "./JobPage";

class FakeEventSource {
  static last: FakeEventSource | null = null;
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  closed = false;
  constructor(public url: string) {
    FakeEventSource.last = this;
  }
  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(fn);
  }
  emit(type: string, data: unknown) {
    for (const fn of this.listeners[type] ?? []) fn(new MessageEvent(type, { data: JSON.stringify(data) }));
  }
  close() {
    this.closed = true;
  }
}

const running: Job = {
  id: "abc", kind: "grow", command: "python -m stem grow --env archive --run runs/archive", run: "archive",
  status: "running", exit_code: null, started: Date.now() / 1000 - 5, finished: null, line_count: 1,
  lines: ["10:00:00 generation 0: scoring the undifferentiated genome on archive training tasks"], first_line: 0,
};

describe("JobPage", () => {
  beforeEach(() => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => setTimeout(() => cb(0), 0));
  });

  it("shows the output so far, then follows the live stream to the end", async () => {
    mockApi({ "GET /api/jobs/abc": running, "GET /api/runs": [], "GET /api/jobs": [] });
    renderAt(<JobPage />, { route: "/jobs/abc", path: "/jobs/:id" });

    expect(await screen.findByRole("heading", { name: "Growing archive" })).toBeInTheDocument();
    expect(screen.getByText("Scoring the undifferentiated genome")).toBeInTheDocument();
    expect(FakeEventSource.last?.url).toBe("/api/jobs/abc/events?since=1");

    await act(async () => {
      FakeEventSource.last!.emit("line", { i: 1, text: "10:00:09 generation 1: development" });
      await new Promise((r) => setTimeout(r, 5));
    });
    expect(screen.getByText("Development is rewriting a copy of the genome")).toBeInTheDocument();
    expect(screen.getByTestId("job-log")).toHaveTextContent("generation 1: development");

    await act(async () => {
      FakeEventSource.last!.emit("line", { i: 2, text: "10:01:00 generation 1: KEPT (training score 1.00)" });
      FakeEventSource.last!.emit("end", { ...running, status: "succeeded", exit_code: 0, finished: Date.now() / 1000 });
      await new Promise((r) => setTimeout(r, 5));
    });
    expect(screen.getByText("Finished", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("g1 kept 1.00")).toBeInTheDocument();
    expect(FakeEventSource.last!.closed).toBe(true);
    expect(screen.queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
  });

  it("stops a running job on request", async () => {
    const calls = mockApi({ "GET /api/jobs/abc": running, "GET /api/runs": [], "GET /api/jobs": [],
      "POST /api/jobs/abc/stop": { ...running } });
    renderAt(<JobPage />, { route: "/jobs/abc", path: "/jobs/:id" });
    (await screen.findByRole("button", { name: "Stop" })).click();
    await screen.findByRole("button", { name: "Stopping" });
    expect(calls.some((c) => c.key === "POST /api/jobs/abc/stop")).toBe(true);
  });

  it("does not open a stream for a job that already ended", async () => {
    FakeEventSource.last = null;
    mockApi({ "GET /api/jobs/abc": { ...running, status: "failed", exit_code: 2, finished: Date.now() / 1000,
      lines: ["error: No API key. Put GROQ_API_KEY=... in .env (see .env.example)."] }, "GET /api/runs": [] });
    renderAt(<JobPage />, { route: "/jobs/abc", path: "/jobs/:id" });
    expect(await screen.findByText("Failed. The output below says why.")).toBeInTheDocument();
    expect(screen.getByTestId("job-log")).toHaveTextContent("No API key");
    expect(FakeEventSource.last).toBeNull();
  });
});
