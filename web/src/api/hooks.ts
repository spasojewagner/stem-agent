import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "./client";
import type { Job, JobRequest, JobStatus } from "./types";

export const keys = {
  config: ["config"] as const,
  environments: ["environments"] as const,
  runs: ["runs"] as const,
  run: (name: string) => ["runs", name] as const,
  genome: (name: string, generation?: number) => ["runs", name, "genome", generation ?? "best"] as const,
  outcomes: (name: string, generation: number) => ["runs", name, "outcomes", generation] as const,
  lineage: (name: string) => ["runs", name, "lineage"] as const,
  diff: (name: string, sha: string) => ["runs", name, "diff", sha] as const,
  evaluation: ["eval"] as const,
  jobs: ["jobs"] as const,
  job: (id: string) => ["jobs", id] as const,
};

export const useConfig = () => useQuery({ queryKey: keys.config, queryFn: api.config, staleTime: 60_000 });
export const useEnvironments = () =>
  useQuery({ queryKey: keys.environments, queryFn: api.environments, staleTime: Infinity });

/** Runs refresh themselves while one of them is growing. */
export const useRuns = () =>
  useQuery({
    queryKey: keys.runs,
    queryFn: api.runs,
    refetchInterval: (q) => (q.state.data?.some((r) => r.active) ? 4000 : false),
  });

export const useRun = (name: string) =>
  useQuery({
    queryKey: keys.run(name),
    queryFn: () => api.run(name),
    refetchInterval: (q) => (q.state.data?.active ? 4000 : false),
  });

export const useGenome = (name: string, generation?: number) =>
  useQuery({ queryKey: keys.genome(name, generation), queryFn: () => api.genome(name, generation) });

export const useOutcomes = (name: string, generation: number | null) =>
  useQuery({
    queryKey: keys.outcomes(name, generation ?? -1),
    queryFn: () => api.outcomes(name, generation!),
    enabled: generation !== null,
    retry: false,
  });

export const useLineage = (name: string) => useQuery({ queryKey: keys.lineage(name), queryFn: () => api.lineage(name) });

export const useDiff = (name: string, sha: string | null) =>
  useQuery({ queryKey: keys.diff(name, sha ?? ""), queryFn: () => api.diff(name, sha!), enabled: !!sha });

export const useEvaluation = () => useQuery({ queryKey: keys.evaluation, queryFn: api.evaluation });

/** The job list, polled so the side rail can show a run that is going on. */
export const useJobs = () =>
  useQuery({
    queryKey: keys.jobs,
    queryFn: api.jobs,
    refetchInterval: (q) => (q.state.data?.some((j) => j.status === "running") ? 3000 : 15_000),
  });

export function useStartJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JobRequest) => api.startJob(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.jobs }),
  });
}

export function useStopJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.stopJob(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.jobs }),
  });
}

export interface JobStream {
  job: Job | null;
  lines: string[];
  status: JobStatus | null;
  error: string | null;
}

/** Output of a job as it is written: the lines so far, then live server-sent events. */
export function useJobStream(id: string): JobStream {
  const qc = useQueryClient();
  const [state, setState] = useState<JobStream>({ job: null, lines: [], status: null, error: null });
  const linesRef = useRef<string[]>([]);

  useEffect(() => {
    let source: EventSource | null = null;
    let cancelled = false;
    linesRef.current = [];

    api.job(id).then(
      (job) => {
        if (cancelled) return;
        linesRef.current = job.lines ?? [];
        const next = (job.first_line ?? 0) + linesRef.current.length;
        setState({ job, lines: linesRef.current, status: job.status, error: null });
        if (job.status !== "running") return;

        source = new EventSource(`/api/jobs/${encodeURIComponent(id)}/events?since=${next}`);
        let pending: string[] = [];
        let frame = 0;
        const flush = () => {
          frame = 0;
          linesRef.current = [...linesRef.current, ...pending];
          pending = [];
          setState((s) => ({ ...s, lines: linesRef.current }));
        };
        source.addEventListener("line", (e) => {
          pending.push(JSON.parse((e as MessageEvent).data).text);
          if (!frame) frame = requestAnimationFrame(flush);
        });
        source.addEventListener("end", (e) => {
          const done: Job = JSON.parse((e as MessageEvent).data);
          if (frame) cancelAnimationFrame(frame);
          flush();
          setState((s) => ({ ...s, job: done, status: done.status }));
          source?.close();
          qc.invalidateQueries({ queryKey: keys.jobs });
          qc.invalidateQueries({ queryKey: keys.runs });
          qc.invalidateQueries({ queryKey: keys.evaluation });
        });
      },
      (err: Error) => !cancelled && setState((s) => ({ ...s, error: err.message })),
    );

    return () => {
      cancelled = true;
      source?.close();
    };
  }, [id, qc]);

  return state;
}
