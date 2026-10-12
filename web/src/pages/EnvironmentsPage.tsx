import { useEnvironments } from "../api/hooks";
import { ErrorBox, LinkButton, Loading, PageHeader, Section } from "../components/ui";

export function EnvironmentsPage() {
  const envs = useEnvironments();
  return (
    <>
      <PageHeader title="Environments"
                  lead="An environment is a place, not a lesson: a short description, raw actions, tasks and a grader. It never says how to succeed. These are the only parts of the code that know anything about a domain." />
      {envs.isPending && <Loading />}
      {envs.error && <ErrorBox error={envs.error} />}
      {envs.data?.map((e) => (
        <Section key={e.name} title={e.name}
                 aside={<LinkButton to={`/grow?env=${e.name}`} className="!px-2.5 !py-1">Grow here</LinkButton>}>
          <p className="max-w-[75ch] leading-relaxed">{e.brief}</p>
          <p className="mt-2 text-sm text-muted">At most {e.max_steps} steps per task.</p>
          <div className="mt-5 grid gap-8 lg:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-semibold">Actions</h3>
              <ul className="space-y-2 text-sm">
                {e.actions.map((a) => (
                  <li key={a.name}>
                    <span className="font-mono font-medium text-hema">{a.name}({a.parameters.join(", ")})</span>
                    <span className="block text-muted">{a.description}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold">Tasks</h3>
              <ul className="space-y-2 text-sm">
                {e.tasks.map((t) => (
                  <li key={t.id} className="flex gap-3">
                    <span className={`mt-0.5 h-fit shrink-0 rounded px-1.5 py-0.5 text-xs ${t.split === "train" ? "bg-hema-soft text-hema" : "bg-sunken text-muted"}`}>
                      {t.split === "train" ? "training" : "held out"}
                    </span>
                    <span><span className="font-medium">{t.id}</span> <span className="text-muted">{t.instruction}</span></span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Section>
      ))}
    </>
  );
}
