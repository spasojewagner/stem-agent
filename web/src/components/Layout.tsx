import { NavLink, Outlet } from "react-router";

import { useConfig, useJobs } from "../api/hooks";

const nav = [
  { to: "/", label: "Runs", end: true },
  { to: "/grow", label: "Grow a genome" },
  { to: "/evaluation", label: "Evaluation" },
  { to: "/environments", label: "Environments" },
];

function Mark() {
  return (
    <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
      <circle cx="16" cy="16" r="13" fill="var(--hema)" />
      <circle cx="16" cy="16" r="5.5" fill="var(--bg)" />
      <circle cx="16" cy="16" r="2.5" fill="var(--eosin)" />
    </svg>
  );
}

export function Layout() {
  const jobs = useJobs();
  const config = useConfig();
  const running = jobs.data?.find((j) => j.status === "running");

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[15rem_1fr]">
      <aside className="border-b border-line bg-surface lg:sticky lg:top-0 lg:h-screen lg:border-r lg:border-b-0">
        <div className="flex h-full flex-col gap-6 px-4 py-4 lg:px-5 lg:py-6">
          <NavLink to="/" className="flex items-center gap-2.5">
            <Mark />
            <span className="text-lg font-semibold tracking-tight">Stem Studio</span>
          </NavLink>
          <nav aria-label="Main" className="flex gap-1 overflow-x-auto lg:flex-col">
            {nav.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end}
                       className={({ isActive }) =>
                         `rounded-md px-3 py-2 text-sm whitespace-nowrap ${isActive
                           ? "bg-hema-soft font-medium text-hema" : "text-muted hover:text-ink"}`}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="mt-auto hidden space-y-3 text-sm lg:block">
            {running && (
              <NavLink to={`/jobs/${running.id}`} className="block rounded-md border border-hema px-3 py-2.5">
                <span className="flex items-center gap-2 font-medium text-hema">
                  <span className="size-1.5 animate-pulse rounded-full bg-hema" aria-hidden />
                  {running.kind === "grow" ? `Growing ${running.run}` : `Running ${running.kind}`}
                </span>
                <span className="text-xs text-muted">Open the live output</span>
              </NavLink>
            )}
            {config.data && (
              <p className="text-xs leading-relaxed text-muted">
                {config.data.api_key_set
                  ? <>Model provider: {config.data.api_host}</>
                  : <>No API key in .env. Selftest and the example runs work without one.</>}
              </p>
            )}
          </div>
        </div>
      </aside>
      <main className="min-w-0 px-4 py-8 sm:px-8 lg:px-12 lg:py-10">
        <div className="mx-auto max-w-6xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
