import { Link } from "react-router";

import { useRuns } from "../api/hooks";
import { ScoreTrail } from "../components/LineageTrack";
import { Empty, ErrorBox, LinkButton, Loading, PageHeader } from "../components/ui";
import { ago, score, tokens } from "../utils/format";

export function RunsPage() {
  const runs = useRuns();

  return (
    <>
      <PageHeader title="Runs"
                  lead="Each run starts from the same empty genome and develops inside one environment. A generation is kept only if it scores better on the training tasks.">
        <LinkButton to="/grow" variant="primary">Grow a genome</LinkButton>
      </PageHeader>

      {runs.isPending && <Loading label="Reading runs" />}
      {runs.error && <ErrorBox error={runs.error} />}
      {runs.data?.length === 0 && (
        <Empty title="No runs yet">
          Grow a genome in one of the environments. To look around without an API key, run{" "}
          <code className="font-mono text-ink">python -m studio.demo</code>, which creates example runs with a scripted model.
        </Empty>
      )}

      {!!runs.data?.length && (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-muted">
              <tr>
                <th className="px-4 py-2.5 font-medium">Run</th>
                <th className="px-4 py-2.5 font-medium">Lineage</th>
                <th className="px-4 py-2.5 text-right font-medium">Generations</th>
                <th className="px-4 py-2.5 text-right font-medium">Training score</th>
                <th className="px-4 py-2.5 text-right font-medium">Tokens</th>
                <th className="px-4 py-2.5 text-right font-medium">Updated</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.map((r) => (
                <tr key={r.name} className="border-b border-line last:border-0 hover:bg-bg">
                  <td className="px-4 py-3">
                    <Link to={`/runs/${encodeURIComponent(r.name)}`} className="font-medium hover:text-hema">
                      {r.name}
                    </Link>
                    <div className="text-xs text-muted">
                      in {r.environment}
                      {r.active && <span className="ml-2 font-medium text-hema">growing now</span>}
                    </div>
                  </td>
                  <td className="px-4 py-3"><ScoreTrail points={r.scores} growing={r.active} /></td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {r.kept} kept of {Math.max(r.generations - 1, 0)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    <span className="text-muted">{score(r.baseline_score)} to </span>
                    <span className="font-semibold">{score(r.best_score)}</span>
                  </td>
                  <td className="px-4 py-3 text-right text-muted tabular-nums">{tokens(r.tokens)}</td>
                  <td className="px-4 py-3 text-right whitespace-nowrap text-muted">{ago(r.updated)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
