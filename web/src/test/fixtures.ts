import type { RunSummary } from "../api/types";

export const exchangeRun: RunSummary = {
  name: "exchange-1",
  environment: "exchange",
  created: "2026-10-10 09:00:00",
  models: { develop: "openai/gpt-oss-120b", act: "openai/gpt-oss-20b" },
  generations: 4,
  kept: 2,
  best_score: 0.71,
  baseline_score: 0,
  tokens: 182_400,
  scores: [
    { generation: 0, score: 0, accepted: true },
    { generation: 1, score: 0, accepted: true },
    { generation: 2, score: 0.71, accepted: true },
    { generation: 3, score: 0.64, accepted: false },
  ],
  updated: Date.now() / 1000 - 120,
  active: false,
};
