import { type FormEvent, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { useConfig, useEnvironments, useJobs, useRuns, useStartJob } from "../api/hooks";
import { Button, ErrorBox, LinkButton, Loading, PageHeader, Section } from "../components/ui";

function NumberField({ id, label, hint, value, min, max, onChange }: {
  id: string; label: string; hint: string; value: number; min: number; max: number; onChange: (n: number) => void;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium">{label}</label>
      <input id={id} type="number" min={min} max={max} value={value}
             onChange={(e) => onChange(Number(e.target.value))}
             className="mt-1 w-28 rounded-md border border-line bg-surface px-2.5 py-1.5 tabular-nums" />
      <p className="mt-1 text-xs text-muted">{hint}</p>
    </div>
  );
}

export function GrowPage() {
  const [params] = useSearchParams();
  const envs = useEnvironments();
  const runs = useRuns();
  const config = useConfig();
  const jobs = useJobs();
  const start = useStartJob();
  const navigate = useNavigate();

  const [env, setEnv] = useState(params.get("env") ?? "archive");
  const [name, setName] = useState(params.get("run") ?? "");
  const [resume] = useState(params.get("resume") === "1");
  const [generations, setGenerations] = useState(resume ? 1 : 3);
  const [devSteps, setDevSteps] = useState(16);
  const [trials, setTrials] = useState(1);
  const [trainTasks, setTrainTasks] = useState(0);

  const runName = name.trim() || env;
  const existing = runs.data?.find((r) => r.name === runName);
  const running = jobs.data?.find((j) => j.status === "running");
  const nameOk = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(runName);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    start.mutate({ kind: "grow", env, run: runName, generations, dev_steps: devSteps, trials,
      train_tasks: trainTasks || null, resume }, { onSuccess: (job) => navigate(`/jobs/${job.id}`) });
  };

  const quick = (kind: "selftest" | "check") =>
    start.mutate({ kind }, { onSuccess: (job) => navigate(`/jobs/${job.id}`) });

  if (envs.isPending) return <Loading />;
  if (envs.error) return <ErrorBox error={envs.error} />;
  const chosen = envs.data.find((e) => e.name === env);

  return (
    <>
      <PageHeader title={resume ? `Continue ${runName}` : "Grow a genome"}
                  lead="Development rewrites a copy of the genome, the copy is scored on the training tasks, and it is kept only if it beats the best genome so far. Held-out tasks are never shown to development." />

      {running && (
        <div className="mb-6 rounded-md border border-hema bg-hema-soft px-4 py-3 text-sm">
          Another job is running. One job runs at a time, because they share the provider's rate limits.{" "}
          <LinkButton to={`/jobs/${running.id}`} className="ml-1 !px-2 !py-0.5">Open it</LinkButton>
        </div>
      )}
      {config.data && !config.data.api_key_set && (
        <div className="mb-6 rounded-md border border-line bg-surface px-4 py-3 text-sm">
          There is no API key in <code className="font-mono">.env</code>, so growing will stop at the first model call.
          The offline selftest below works without one.
        </div>
      )}

      <form onSubmit={submit} className="grid grid-cols-[minmax(0,1fr)] gap-10 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div>
          <fieldset disabled={resume}>
            <legend className="mb-3 font-semibold">Environment</legend>
            <div className="grid gap-3 sm:grid-cols-3">
              {envs.data.map((e) => (
                <label key={e.name}
                       className={`cursor-pointer rounded-lg border px-4 py-3 transition-colors ${env === e.name
                         ? "border-hema bg-hema-soft" : "border-line bg-surface hover:border-muted"} ${resume && env !== e.name ? "opacity-40" : ""}`}>
                  <input type="radio" name="env" value={e.name} checked={env === e.name}
                         onChange={() => setEnv(e.name)} className="sr-only" />
                  <span className="block font-medium">{e.name}</span>
                  <span className="mt-1 block text-xs text-muted">
                    {e.tasks.filter((t) => t.split === "train").length} training,{" "}
                    {e.tasks.filter((t) => t.split === "test").length} held-out tasks
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          {chosen && <p className="mt-4 max-w-[72ch] text-sm leading-relaxed text-muted">{chosen.brief}</p>}

          <Section title="Settings" className="mt-10">
            <div className="grid gap-6 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label htmlFor="run-name" className="block text-sm font-medium">Run folder</label>
                <input id="run-name" value={name} placeholder={env} disabled={resume}
                       onChange={(e) => setName(e.target.value)}
                       className="mt-1 w-full max-w-sm rounded-md border border-line bg-surface px-2.5 py-1.5" />
                <p className="mt-1 text-xs text-muted">
                  {!nameOk ? <span className="text-eosin">Use letters, digits, dots, dashes and underscores.</span>
                    : existing && !resume ? <span className="text-eosin">runs/{runName} exists and will be started over. Continue it from its page instead to keep it.</span>
                      : `Saved in runs/${runName}`}
                </p>
              </div>
              <NumberField id="gens" label={resume ? "More generations" : "Generations"} value={generations} min={1} max={20}
                           onChange={setGenerations} hint="Each one is a round of development and scoring." />
              <NumberField id="steps" label="Development steps" value={devSteps} min={4} max={40}
                           onChange={setDevSteps} hint="Tool calls development may make per generation." />
              <NumberField id="trials" label="Trial runs" value={trials} min={0} max={5}
                           onChange={setTrials} hint="Times development may try the agent on a task." />
              <NumberField id="train" label="Training tasks" value={trainTasks} min={0} max={10}
                           onChange={setTrainTasks} hint="0 uses all of them. Fewer saves quota." />
            </div>
          </Section>

          {start.error && <div className="mb-4"><ErrorBox error={start.error} /></div>}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" variant="primary" disabled={!!running || start.isPending || !nameOk}>
              {resume ? "Continue growing" : "Start growing"}
            </Button>
            {resume && <LinkButton to="/grow" reloadDocument>Start a new run instead</LinkButton>}
          </div>
        </div>

        <aside className="space-y-6 text-sm">
          <div>
            <h2 className="mb-1 font-semibold">Before a long run</h2>
            <p className="text-muted">The selftest checks the sandbox and graders without calling a model. The model check makes one small tool-calling request per model.</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button type="button" onClick={() => quick("selftest")} disabled={!!running || start.isPending}>Run selftest</Button>
              <Button type="button" onClick={() => quick("check")} disabled={!!running || start.isPending}>Check models</Button>
            </div>
          </div>
          {config.data && (
            <div>
              <h2 className="mb-1 font-semibold">Models</h2>
              <dl className="space-y-1 text-muted">
                <div>Development: <span className="text-ink">{config.data.models.develop}</span></div>
                <div>Acting: <span className="text-ink">{config.data.models.act}</span></div>
                <div>Specialists: <span className="text-ink">{config.data.models.fast}</span></div>
              </dl>
              <p className="mt-2 text-muted">A run stops at {config.data.token_budget.toLocaleString()} tokens and can be continued later. Set these in <code className="font-mono">.env</code>.</p>
            </div>
          )}
        </aside>
      </form>
    </>
  );
}
