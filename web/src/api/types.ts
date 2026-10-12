export interface ScorePoint {
  generation: number;
  score: number;
  accepted: boolean;
}

export interface RunSummary {
  name: string;
  environment: string;
  created: string;
  models: Record<string, string>;
  generations: number;
  kept: number;
  best_score: number;
  baseline_score: number | null;
  tokens: number;
  scores: ScorePoint[];
  updated: number;
  active: boolean;
}

export interface Generation {
  generation: number;
  accepted: boolean;
  train_score: number;
  per_task: Record<string, number>;
  summary: string;
  fingerprint: string;
  tokens_used: number;
  seconds: number;
}

export interface Note {
  generation: number | null;
  text: string;
}

export interface GenomeTool {
  name: string;
  description: string;
  parameters: { properties?: Record<string, { type?: string; description?: string }>; required?: string[] };
  code: string;
}

export interface Genome {
  identity: string;
  system_prompt: string;
  mode: Record<string, string | number | boolean>;
  tools: GenomeTool[];
  skills: { name: string; content: string }[];
  subagents: { name: string; purpose: string; system_prompt: string; tools: string[]; max_steps: number }[];
  hooks: { event: string; code: string }[];
  fingerprint: string;
  is_stem: boolean;
}

export interface RunDetail extends RunSummary {
  history: Generation[];
  notebook: Note[];
  genome: Genome | null;
  candidates: number[];
}

export interface TaskOutcome {
  task: string;
  score: number;
  note: string;
  stopped: string;
  steps: number;
  final: string;
  digest: string;
}

export interface Commit {
  sha: string;
  short: string;
  date: string;
  subject: string;
  body: string;
  files: { path: string; added: number; removed: number }[];
}

export interface EnvironmentInfo {
  name: string;
  brief: string;
  max_steps: number;
  actions: { name: string; description: string; parameters: string[] }[];
  tasks: { id: string; split: "train" | "test"; instruction: string }[];
}

export interface EvalMatrix {
  split: string;
  table: Record<string, Record<string, number>>;
  details: Record<string, Record<string, { task: string; score: number; note: string }[]>>;
  updated: number;
}

export interface StudioConfig {
  api_host: string;
  api_key_set: boolean;
  models: Record<string, string>;
  token_budget: number;
  runs_dir: string;
}

export type JobKind = "grow" | "selftest" | "check" | "baseline" | "matrix";
export type JobStatus = "running" | "succeeded" | "failed" | "stopped";

export interface Job {
  id: string;
  kind: JobKind;
  command: string;
  run: string | null;
  status: JobStatus;
  exit_code: number | null;
  started: number;
  finished: number | null;
  line_count: number;
  lines?: string[];
  first_line?: number;
}

export interface JobRequest {
  kind: JobKind;
  env?: string;
  run?: string;
  generations?: number;
  dev_steps?: number;
  trials?: number;
  train_tasks?: number | null;
  resume?: boolean;
  envs?: string[];
  runs?: string[];
  split?: "train" | "test";
}
