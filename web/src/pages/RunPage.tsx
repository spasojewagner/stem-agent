import { useState } from "react";
import { Link, useParams } from "react-router";

import { useDiff, useGenome, useJobs, useLineage, useOutcomes, useRun } from "../api/hooks";
import type { Generation, RunDetail } from "../api/types";
import { DiffView } from "../components/Code";
import { GenomeView } from "../components/GenomeView";
import { LineageTrack } from "../components/LineageTrack";
import { ErrorBox, LinkButton, Loading, PageHeader, Section, Stat } from "../components/ui";
import { duration, score, tokens } from "../utils/format";
import { stain, stainText } from "../utils/scale";

type Tab = "genome" | "changes" | "notes";

export function RunPage() {
  const { name = "" } = useParams();
  const run = useRun(name);
  const [selected, setSelected] = useState<number | null>(null);
  const [tab, setTab] = useState<Tab>("genome");
  const [genomeOf, setGenomeOf] = useState<number | undefined>(undefined);

  if (run.isPending) return <Loading label="Reading the run" />;
  if (run.error) return <ErrorBox error={run.error} />;
  const r = run.data;
  const current = selected ?? r.history.at(-1)?.generation ?? 0;
  const gen = r.history.find((g) => g.generation === current);

  const inspect = (g: number) => {
    setGenomeOf(g);
    setTab("genome");
    document.getElementById("run-tabs")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <>
      <PageHeader title={r.name}
                  lead={<>Grown in <Link to="/environments" className="text-ink underline decoration-line underline-offset-4 hover:decoration-hema">{r.environment}</Link> since {r.created}. Development model {r.models.develop ?? "unknown"}, acting model {r.models.act ?? "unknown"}.</>}>
        <ContinueButton run={r} />
      </PageHeader>

      <div className="mb-10 grid grid-cols-2 gap-6 sm:grid-cols-4">
        <Stat label="Undifferentiated" value={score(r.baseline_score)} hint="training score at generation 0" />
        <Stat label="Best so far" value={score(r.best_score)} hint="training score of the kept genome" />
        <Stat label="Kept changes" value={`${r.kept} of ${Math.max(r.generations - 1, 0)}`} hint="generations accepted" />
        <Stat label="Tokens" value={tokens(r.tokens)} hint="all generations" />
      </div>

      <Section title="Lineage" aside="Select a generation to see what development did">
        <div className="rounded-lg border border-line bg-surface px-2 pt-2">
          <LineageTrack points={r.scores} selected={current} onSelect={setSelected} growing={r.active} />
        </div>
        {gen && <GenerationPanel run={r} gen={gen} onInspect={inspect} />}
      </Section>

      <div id="run-tabs" className="scroll-mt-6">
        <div role="tablist" aria-label="Run details" className="mb-5 flex gap-1 border-b border-line">
          {([["genome", "Genome"], ["changes", "Changes"], ["notes", `Notes (${r.notebook.length})`]] as const).map(([id, label]) => (
            <button key={id} role="tab" aria-selected={tab === id} id={`tab-${id}`} aria-controls={`panel-${id}`}
                    onClick={() => setTab(id)}
                    className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === id
                      ? "border-hema font-medium text-ink" : "border-transparent text-muted hover:text-ink"}`}>
              {label}
            </button>
          ))}
        </div>
        <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
          {tab === "genome" && <GenomeTab run={r} generation={genomeOf} onChange={setGenomeOf} />}
          {tab === "changes" && <ChangesTab name={r.name} />}
          {tab === "notes" && <NotesTab run={r} />}
        </div>
      </div>
    </>
  );
}

function ContinueButton({ run }: { run: RunDetail }) {
  const jobs = useJobs();
  const job = jobs.data?.find((j) => j.status === "running" && j.run === run.name);
  if (job) return <LinkButton to={`/jobs/${job.id}`} variant="primary">Watch it grow</LinkButton>;
  const q = new URLSearchParams({ env: run.environment, run: run.name, resume: "1" });
  return <LinkButton to={`/grow?${q}`}>Continue growing</LinkButton>;
}

function GenerationPanel({ run, gen, onInspect }: { run: RunDetail; gen: Generation; onInspect: (g: number) => void }) {
  const outcomes = useOutcomes(run.name, gen.generation);
  const verdict = gen.generation === 0 ? "The undifferentiated stem"
    : gen.accepted ? "Kept: it became the genome later generations start from"
      : "Discarded: it did not beat the genome it was developed from";
  const hasCandidate = run.candidates.includes(gen.generation);

  return (
    <div className="mt-5 grid grid-cols-[minmax(0,1fr)] gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div>
        <h3 className="text-lg font-semibold">Generation {gen.generation}</h3>
        <p className={`text-sm ${gen.accepted ? "text-hema" : "text-eosin"}`}>{verdict}</p>
        <p className="mt-3 max-w-[68ch] leading-relaxed whitespace-pre-wrap">{gen.summary}</p>
        <p className="mt-3 text-sm text-muted">
          Training score {score(gen.train_score)}, {tokens(gen.tokens_used)} tokens, {duration(gen.seconds)}
        </p>
        {hasCandidate && (
          <button onClick={() => onInspect(gen.generation)} className="mt-3 text-sm font-medium text-hema hover:underline">
            Inspect the genome this generation produced
          </button>
        )}
      </div>
      <div>
        <h4 className="mb-2 text-sm font-medium text-muted">Training tasks</h4>
        {outcomes.isPending && <p className="text-sm text-muted">Loading</p>}
        {outcomes.isError && <p className="text-sm text-muted">Not scored: development did not change the genome.</p>}
        {outcomes.data?.length === 0 && <p className="text-sm text-muted">Not scored in this generation.</p>}
        <ul className="space-y-2">
          {outcomes.data?.map((o) => (
            <li key={o.task}>
              <details className="rounded-md border border-line bg-surface">
                <summary className="flex cursor-pointer items-center gap-3 px-3 py-2 text-sm">
                  <span className="inline-block w-12 shrink-0 rounded px-1.5 py-0.5 text-center text-xs font-semibold tabular-nums"
                        style={{ background: stain(o.score), color: stainText(o.score) }}>{score(o.score)}</span>
                  <span className="shrink-0 font-medium whitespace-nowrap">{o.task}</span>
                  <span className="min-w-0 truncate text-muted">{o.note}</span>
                </summary>
                <pre className="overflow-x-auto border-t border-line px-3 py-2 font-mono text-xs leading-relaxed whitespace-pre-wrap">{o.digest}</pre>
              </details>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function GenomeTab({ run, generation, onChange }: { run: RunDetail; generation?: number; onChange: (g?: number) => void }) {
  const genome = useGenome(run.name, generation);
  const gen = run.history.find((g) => g.generation === generation);
  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center gap-3 text-sm">
        <label htmlFor="genome-of" className="text-muted">Showing</label>
        <select id="genome-of" value={generation ?? ""} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : undefined)}
                className="rounded-md border border-line bg-surface px-2.5 py-1.5">
          <option value="">the best genome</option>
          {run.candidates.map((g) => {
            const h = run.history.find((x) => x.generation === g);
            return <option key={g} value={g}>the candidate from generation {g}{h ? (h.accepted ? ", kept" : ", discarded") : ""}</option>;
          })}
        </select>
        {gen && !gen.accepted && <span className="text-eosin">This candidate was discarded.</span>}
        {genome.data && <span className="text-xs text-muted">fingerprint {genome.data.fingerprint}</span>}
      </div>
      {genome.isPending && <Loading />}
      {genome.error && <ErrorBox error={genome.error} />}
      {genome.data && <GenomeView genome={genome.data} />}
    </div>
  );
}

function ChangesTab({ name }: { name: string }) {
  const lineage = useLineage(name);
  const [sha, setSha] = useState<string | null>(null);
  const commits = lineage.data ?? [];
  const active = sha ?? commits.at(-1)?.sha ?? null;
  const diff = useDiff(name, active);

  if (lineage.isPending) return <Loading />;
  if (lineage.error) return <ErrorBox error={lineage.error} />;
  if (!commits.length) return <p className="text-muted">The genome has no history (git was not available when it grew).</p>;

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[18rem_minmax(0,1fr)]">
      <ol className="space-y-1">
        {commits.map((c) => (
          <li key={c.sha}>
            <button onClick={() => setSha(c.sha)} aria-current={active === c.sha}
                    className={`w-full rounded-md px-3 py-2 text-left text-sm ${active === c.sha
                      ? "bg-hema-soft" : "hover:bg-sunken"}`}>
              <span className="block font-medium">{c.subject}</span>
              <span className="text-xs text-muted">
                {c.files.length} {c.files.length === 1 ? "file" : "files"},{" "}
                +{c.files.reduce((n, f) => n + f.added, 0)} −{c.files.reduce((n, f) => n + f.removed, 0)}
              </span>
            </button>
          </li>
        ))}
      </ol>
      <div className="min-w-0">
        {(() => {
          const c = commits.find((x) => x.sha === active);
          return c?.body ? <p className="mb-4 max-w-[72ch] leading-relaxed whitespace-pre-wrap">{c.body}</p> : null;
        })()}
        {diff.isPending && <Loading label="Reading the change" />}
        {diff.error && <ErrorBox error={diff.error} />}
        {diff.data && <DiffView diff={diff.data.diff} />}
      </div>
    </div>
  );
}

function NotesTab({ run }: { run: RunDetail }) {
  if (!run.notebook.length) {
    return <p className="text-muted">Development has not written notes in this run yet.</p>;
  }
  const byGen = new Map<number, string[]>();
  for (const n of run.notebook) {
    const g = n.generation ?? 0;
    byGen.set(g, [...(byGen.get(g) ?? []), n.text]);
  }
  return (
    <div className="space-y-6">
      <p className="max-w-[68ch] text-sm text-muted">
        Development writes these for itself as it works. The latest ones are shown to every later generation, so a
        diagnosis survives a generation that runs out of steps.
      </p>
      {[...byGen.entries()].map(([g, notes]) => (
        <div key={g}>
          <h3 className="mb-2 text-sm font-semibold">Generation {g}</h3>
          <ul className="max-w-[72ch] space-y-2 border-l-2 border-hema-soft pl-4">
            {notes.map((t, i) => <li key={i} className="leading-relaxed">{t}</li>)}
          </ul>
        </div>
      ))}
    </div>
  );
}
