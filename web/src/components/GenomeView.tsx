import type { Genome } from "../api/types";
import { CodeBlock } from "./Code";

function Block({ title, children, count }: { title: string; children: React.ReactNode; count?: number }) {
  return (
    <div className="border-t border-line py-5 first:border-t-0 first:pt-0">
      <h3 className="mb-2 font-semibold">
        {title}
        {count !== undefined && <span className="ml-2 font-normal text-muted">{count}</span>}
      </h3>
      {children}
    </div>
  );
}

const modeLabels: Record<string, string> = {
  max_steps: "Steps per task",
  temperature: "Temperature",
  plan_first: "Plans before acting",
  reflect_every: "Reflects every N steps",
  model_tier: "Model tier",
};

export function GenomeView({ genome }: { genome: Genome }) {
  if (genome.is_stem) {
    return (
      <p className="text-muted">
        Still the undifferentiated stem: no identity, no instructions, no tools or procedures of its own.
      </p>
    );
  }
  return (
    <div>
      <Block title="Identity">
        <p className="max-w-[72ch] leading-relaxed">{genome.identity || <span className="text-muted">Not set</span>}</p>
      </Block>
      <Block title="Working instructions">
        {genome.system_prompt
          ? <p className="max-w-[72ch] leading-relaxed whitespace-pre-wrap">{genome.system_prompt}</p>
          : <p className="text-muted">Not set</p>}
      </Block>
      <Block title="Behaviour">
        <dl className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm sm:grid-cols-3 lg:grid-cols-5">
          {Object.entries(genome.mode).map(([k, v]) => (
            <div key={k}>
              <dt className="text-muted">{modeLabels[k] ?? k}</dt>
              <dd className="font-medium tabular-nums">{typeof v === "boolean" ? (v ? "yes" : "no") : String(v)}</dd>
            </div>
          ))}
        </dl>
      </Block>
      <Block title="Tools it wrote" count={genome.tools.length}>
        {genome.tools.length === 0 ? <p className="text-sm text-muted">None</p> : (
          <div className="space-y-4">
            {genome.tools.map((t) => (
              <details key={t.name} className="group" open={genome.tools.length === 1}>
                <summary className="cursor-pointer list-none">
                  <span className="font-mono text-sm font-medium text-hema">{t.name}(
                    {Object.keys(t.parameters.properties ?? {}).join(", ")})</span>
                  <span className="ml-3 text-sm text-muted">{t.description}</span>
                </summary>
                <div className="mt-2"><CodeBlock code={t.code} label={`tools/${t.name}.py`} /></div>
              </details>
            ))}
          </div>
        )}
      </Block>
      <Block title="Procedures" count={genome.skills.length}>
        {genome.skills.length === 0 ? <p className="text-sm text-muted">None</p> : (
          <div className="space-y-3">
            {genome.skills.map((s) => (
              <div key={s.name}>
                <div className="mb-1 text-sm font-medium">{s.name}</div>
                <p className="max-w-[72ch] rounded-md bg-sunken px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap">{s.content}</p>
              </div>
            ))}
          </div>
        )}
      </Block>
      <Block title="Specialists" count={genome.subagents.length}>
        {genome.subagents.length === 0 ? <p className="text-sm text-muted">None</p> : (
          <ul className="space-y-3">
            {genome.subagents.map((s) => (
              <li key={s.name}>
                <span className="font-medium">{s.name}</span>
                <span className="ml-2 text-sm text-muted">{s.purpose}</span>
                <p className="mt-1 max-w-[72ch] text-sm whitespace-pre-wrap">{s.system_prompt}</p>
                {s.tools.length > 0 && <p className="mt-1 text-xs text-muted">Can use: {s.tools.join(", ")}</p>}
              </li>
            ))}
          </ul>
        )}
      </Block>
      <Block title="Hooks" count={genome.hooks.length}>
        {genome.hooks.length === 0 ? <p className="text-sm text-muted">None</p> : (
          <div className="space-y-3">
            {genome.hooks.map((h) => <CodeBlock key={h.event} code={h.code} label={`hooks/${h.event}.py`} />)}
          </div>
        )}
      </Block>
    </div>
  );
}
