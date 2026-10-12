import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router";

import { useJobStream, useRuns, useStopJob } from "../api/hooks";
import { Button, ErrorBox, LinkButton, Loading, PageHeader, StatusBadge } from "../components/ui";
import { duration, score } from "../utils/format";
import type { JobStatus } from "../api/types";
import { parseProgress, type Progress } from "../utils/progress";

const phaseText: Record<Progress["phase"], string> = {
  starting: "Starting",
  baseline: "Scoring the undifferentiated genome",
  development: "Development is rewriting a copy of the genome",
  scoring: "Scoring the candidate on the training tasks",
  waiting: "Waiting for the rate limit",
  done: "Finished",
  stopped: "Stopped",
};

function useNow(active: boolean) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

export function JobPage() {
  const { id = "" } = useParams();
  const { job, lines, status, error } = useJobStream(id);
  const runs = useRuns();
  const stop = useStopJob();
  const progress = useMemo(() => parseProgress(lines), [lines]);
  const now = useNow(status === "running");
  const logRef = useRef<HTMLPreElement>(null);
  const [follow, setFollow] = useState(true);

  useEffect(() => {
    const el = logRef.current;
    if (el && follow) el.scrollTop = el.scrollHeight;
  }, [lines, follow]);

  if (error) return <ErrorBox error={error} />;
  if (!job || !status) return <Loading label="Connecting to the job" />;

  const elapsed = ((job.finished ? job.finished * 1000 : now) - job.started * 1000) / 1000;
  const isGrow = job.kind === "grow";

  return (
    <>
      <PageHeader title={isGrow ? `Growing ${job.run}` : job.kind === "selftest" ? "Selftest" : job.kind === "check" ? "Model check" : `Evaluation: ${job.kind}`}
                  lead={<code className="block overflow-x-auto font-mono text-sm whitespace-nowrap">{job.command}</code>}>
        {status === "running" && (
          <Button variant="danger" onClick={() => stop.mutate(job.id)} disabled={stop.isPending || stop.isSuccess}>
            {stop.isPending || stop.isSuccess ? "Stopping" : "Stop"}
          </Button>
        )}
        {status !== "running" && isGrow && job.run && runs.data?.some((r) => r.name === job.run) && <LinkButton to={`/runs/${encodeURIComponent(job.run)}`} variant="primary">Open the run</LinkButton>}
        {status !== "running" && job.kind === "matrix" && <LinkButton to="/evaluation" variant="primary">See the matrix</LinkButton>}
      </PageHeader>

      <div className="mb-6 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <StatusBadge status={status} />
        <span className="text-muted tabular-nums">{duration(elapsed)}</span>
        {job.exit_code !== null && <span className="text-muted">exit code {job.exit_code}</span>}
      </div>

      {status === "running" && (
        <p className="mb-6 max-w-[70ch] text-sm text-muted">
          Stop works like Ctrl+C: finished generations and development notes are saved
          {job.run ? ", and the run can be continued from its page." : "."}
        </p>
      )}
      {status === "stopped" && job.run && (
        <p className="mb-6 text-sm">
          Progress is saved. <Link to={`/runs/${encodeURIComponent(job.run)}`} className="text-hema hover:underline">Open the run</Link> and
          choose Continue growing to resume.
        </p>
      )}

      {isGrow && <GrowProgress progress={progress} status={status} />}

      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-semibold">Output</h2>
        <label className="flex items-center gap-2 text-sm text-muted">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
          Follow new lines
        </label>
      </div>
      <pre ref={logRef} aria-live="off" data-testid="job-log"
           className="h-[28rem] overflow-auto rounded-lg border border-line bg-code px-4 py-3 font-mono text-[12.5px] leading-relaxed">
        {lines.length === 0 ? <span className="text-muted">No output yet.</span> : lines.map((l, i) => (
          <div key={i} className={/KEPT|selftest passed/.test(l) ? "font-semibold text-hema"
            : /discarded|^(\S+ )?!! |Stopped|^error/i.test(l) ? "text-eosin" : ""}>{l || " "}</div>
        ))}
      </pre>
    </>
  );
}

function GrowProgress({ progress: p, status }: { progress: Progress; status: JobStatus }) {
  const headline = status === "running" ? (p.waiting ? phaseText.waiting : phaseText[p.phase])
    : status === "failed" ? "Failed. The output below says why."
      : status === "stopped" ? phaseText.stopped : phaseText.done;
  return (
    <div className="mb-8 grid gap-6 rounded-lg border border-line bg-surface px-5 py-4 sm:grid-cols-[minmax(0,1fr)_auto]">
      <div className="min-w-0">
        {p.generation !== null && <div className="text-sm text-muted">Generation {p.generation}</div>}
        <div className="font-medium">{headline}</div>
        {status === "running" && (
          <div className="mt-1 truncate text-sm text-muted">
            {p.waiting ? p.waiting : p.task ? `Task ${p.task}` : p.lastStep ?? ""}
          </div>
        )}
      </div>
      {p.results.length > 0 && (
        <ol className="flex flex-wrap gap-2 self-center" aria-label="Generations finished in this job">
          {p.results.map((r) => (
            <li key={r.generation}
                className={`rounded-md px-2.5 py-1 text-xs tabular-nums ${r.kept ? "bg-hema-soft text-hema" : "bg-eosin-soft text-eosin"}`}>
              g{r.generation} {r.kept ? "kept" : "discarded"} {score(r.score)}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
