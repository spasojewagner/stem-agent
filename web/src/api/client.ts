import type {
  Commit, EnvironmentInfo, EvalMatrix, Genome, Job, JobRequest, RunDetail, RunSummary, StudioConfig, TaskOutcome,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function describe(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{loc, msg}]
    return detail.map((d) => (typeof d === "object" && d && "msg" in d ? String(d.msg) : String(d))).join("; ");
  }
  return "Request failed";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      message = describe((await res.json()).detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

const enc = encodeURIComponent;

export const api = {
  config: () => request<StudioConfig>("/config"),
  environments: () => request<EnvironmentInfo[]>("/environments"),
  runs: () => request<RunSummary[]>("/runs"),
  run: (name: string) => request<RunDetail>(`/runs/${enc(name)}`),
  genome: (name: string, generation?: number) =>
    request<Genome>(`/runs/${enc(name)}/genome${generation ? `?generation=${generation}` : ""}`),
  outcomes: (name: string, generation: number) =>
    request<TaskOutcome[]>(`/runs/${enc(name)}/generations/${generation}`),
  lineage: (name: string) => request<Commit[]>(`/runs/${enc(name)}/lineage`),
  diff: (name: string, sha: string) => request<{ sha: string; diff: string }>(`/runs/${enc(name)}/lineage/${enc(sha)}`),
  evaluation: () => request<EvalMatrix | null>("/eval"),
  jobs: () => request<Job[]>("/jobs"),
  job: (id: string) => request<Job>(`/jobs/${enc(id)}`),
  startJob: (body: JobRequest) => request<Job>("/jobs", { method: "POST", body: JSON.stringify(body) }),
  stopJob: (id: string) => request<Job>(`/jobs/${enc(id)}/stop`, { method: "POST" }),
};
