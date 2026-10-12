import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router";

import { useEnvironments, useEvaluation, useJobs, useRuns, useStartJob } from "../api/hooks";
import { Button, Empty, ErrorBox, Loading, PageHeader, Section } from "../components/ui";
import { ago, score } from "../utils/format";
import { stain, stainText } from "../utils/scale";

export function EvaluationPage() {
  const evaluation = useEvaluation();
  const envs = useEnvironments();

  return (
    <>
      <PageHeader title="Evaluation"
                  lead="Genomes against environments, on held-out tasks that development never saw. The stem row should stay near zero, each grown genome should be strong in its own environment, and weak in the others: the same code became different agents." />

      {evaluation.isPending && <Loading />}
      {evaluation.error && <ErrorBox error={evaluation.error} />}
      {evaluation.data === null && (
        <Empty title="No matrix yet">Choose grown runs below to compare them with the undifferentiated stem.</Empty>
      )}
      {evaluation.data && (
        <Section title={`Mean score on ${evaluation.data.split === "test" ? "held-out" : "training"} tasks`}
                 aside={`computed ${ago(evaluation.data.updated)}`}>
          <Matrix table={evaluation.data.table} details={evaluation.data.details}
                  envOrder={envs.data?.map((e) => e.name)} />
        </Section>
      )}

      <ComputeForm />
    </>
  );
}

function Matrix({ table, details, envOrder }: {
  table: Record<string, Record<string, number>>;
  details: Record<string, Record<string, { task: string; score: number; note: string }[]>>;
  envOrder?: string[];
}) {
  const rows = Object.keys(table);
  const present = new Set(rows.flatMap((r) => Object.keys(table[r])));
  const cols = (envOrder ?? [...present]).filter((e) => present.has(e));
  const home = (row: string) => row.replace(/^grown in /, "");

  return (
    <div className="overflow-x-auto">
      <table className="text-sm">
        <thead>
          <tr>
            <th className="px-3 py-2 text-left font-medium text-muted">Genome</th>
            {cols.map((c) => <th key={c} className="px-3 py-2 text-center font-medium">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row}>
              <th scope="row" className="px-3 py-1.5 text-left font-medium whitespace-nowrap">{row}</th>
              {cols.map((c) => {
                const v = table[row][c];
                const tasks = details[row]?.[c] ?? [];
                const diagonal = home(row) === c;
                return (
                  <td key={c} className="p-1">
                    <div title={tasks.map((t) => `${t.task}: ${score(t.score)} ${t.note}`).join("\n")}
                         className={`w-28 rounded-md px-3 py-3 text-center text-base font-semibold tabular-nums ${diagonal ? "ring-2 ring-ink ring-offset-2 ring-offset-bg" : ""}`}
                         style={{ background: stain(v ?? 0), color: stainText(v ?? 0) }}>
                      {score(v)}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-xs text-muted">Outlined cells are each genome's own environment. Hover a cell for per-task scores.</p>
    </div>
  );
}

function ComputeForm() {
  const runs = useRuns();
  const jobs = useJobs();
  const start = useStartJob();
  const navigate = useNavigate();
  const [picked, setPicked] = useState<string[]>([]);
  const [split, setSplit] = useState<"test" | "train">("test");
  const running = jobs.data?.some((j) => j.status === "running");
  const grown = (runs.data ?? []).filter((r) => r.kept > 0);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    start.mutate({ kind: "matrix", runs: picked, split }, { onSuccess: (j) => navigate(`/jobs/${j.id}`) });
  };

  return (
    <Section title="Compute a matrix">
      <form onSubmit={submit} className="space-y-4">
        {grown.length === 0
          ? <p className="text-sm text-muted">There are no runs with a kept change yet.</p>
          : (
            <fieldset>
              <legend className="mb-2 text-sm text-muted">Grown genomes to compare</legend>
              <div className="flex flex-wrap gap-2">
                {grown.map((r) => (
                  <label key={r.name} className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm ${picked.includes(r.name) ? "border-hema bg-hema-soft" : "border-line bg-surface"}`}>
                    <input type="checkbox" checked={picked.includes(r.name)}
                           onChange={(e) => setPicked(e.target.checked ? [...picked, r.name] : picked.filter((p) => p !== r.name))} />
                    {r.name} <span className="text-muted">({r.environment})</span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input type="radio" name="split" checked={split === "test"} onChange={() => setSplit("test")} /> Held-out tasks
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" name="split" checked={split === "train"} onChange={() => setSplit("train")} /> Training tasks
          </label>
        </div>
        {start.error && <ErrorBox error={start.error} />}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" variant="primary" disabled={!picked.length || running || start.isPending}>Compute matrix</Button>
          <Button type="button" disabled={running || start.isPending}
                  onClick={() => start.mutate({ kind: "baseline", split }, { onSuccess: (j) => navigate(`/jobs/${j.id}`) })}>
            Score only the stem
          </Button>
        </div>
        <p className="text-xs text-muted">Results are cached per genome and task, so an interrupted matrix continues where it stopped.</p>
      </form>
    </Section>
  );
}
