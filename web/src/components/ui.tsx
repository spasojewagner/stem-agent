import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router";

import type { JobStatus } from "../api/types";

type Variant = "primary" | "quiet" | "danger";

const variants: Record<Variant, string> = {
  primary: "bg-hema text-surface hover:brightness-110 disabled:opacity-50",
  quiet: "border border-line bg-surface text-ink hover:border-hema hover:text-hema disabled:opacity-50",
  danger: "border border-eosin text-eosin hover:bg-eosin-soft disabled:opacity-50",
};

const base =
  "inline-flex items-center justify-center gap-2 rounded-md px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed";

export function Button({ variant = "quiet", className = "", ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return <button className={`${base} ${variants[variant]} ${className}`} {...rest} />;
}

export function LinkButton({ variant = "quiet", className = "", ...rest }: LinkProps & { variant?: Variant }) {
  return <Link className={`${base} ${variants[variant]} ${className}`} {...rest} />;
}

const statusStyle: Record<JobStatus, string> = {
  running: "bg-hema-soft text-hema",
  succeeded: "bg-sunken text-ok",
  failed: "bg-eosin-soft text-eosin",
  stopped: "bg-sunken text-muted",
};

const statusText: Record<JobStatus, string> = {
  running: "Running",
  succeeded: "Finished",
  failed: "Failed",
  stopped: "Stopped, resumable",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${statusStyle[status]}`}>
      {status === "running" && <span className="size-1.5 animate-pulse rounded-full bg-current" aria-hidden />}
      {statusText[status]}
    </span>
  );
}

export function PageHeader({ title, children, lead }: { title: ReactNode; lead?: ReactNode; children?: ReactNode }) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[1.75rem] leading-tight font-semibold tracking-tight">{title}</h1>
        {lead && <p className="mt-1.5 max-w-[68ch] text-muted">{lead}</p>}
      </div>
      {children && <div className="flex flex-wrap gap-2">{children}</div>}
    </header>
  );
}

export function Section({ title, aside, children, className = "" }: {
  title: ReactNode; aside?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`mb-10 ${className}`}>
      <div className="mb-3 flex items-baseline justify-between gap-4 border-b border-line pb-2">
        <h2 className="text-base font-semibold">{title}</h2>
        {aside && <div className="text-sm text-muted">{aside}</div>}
      </div>
      {children}
    </section>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="rounded-md border border-eosin bg-eosin-soft px-4 py-3 text-sm text-eosin">
      {message}
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-10 text-sm text-muted" role="status">
      <span className="size-2 animate-pulse rounded-full bg-hema" aria-hidden />
      {label}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line px-6 py-10">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-2 max-w-[64ch] text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div>
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-0.5 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="text-xs text-muted">{hint}</div>}
    </div>
  );
}
