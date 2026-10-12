import { type KeyboardEvent, useEffect, useRef, useState } from "react";

import type { ScorePoint } from "../api/types";
import { score as fmt } from "../utils/format";
import { stain } from "../utils/scale";

/**
 * How a genome grew. Kept generations sit on the main line, sized and stained by
 * their training score. A discarded candidate branches off the genome it was
 * developed from and ends there.
 */
export function LineageTrack({ points, selected, onSelect, growing = false }: {
  points: ScorePoint[];
  selected?: number | null;
  onSelect?: (generation: number) => void;
  growing?: boolean;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [available, setAvailable] = useState(0);
  useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => setAvailable(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const left = 34;
  const slots = Math.max(points.length - 1 + (growing ? 1 : 0), 1);
  // Spread a short lineage across the box; a long one keeps a readable spacing and scrolls.
  const step = Math.max(64, Math.min(220, available ? (available - left * 2) / slots : 76));
  const mainY = 104;
  const branchY = 40;
  const width = Math.max(left * 2 + step * slots, 320);
  const x = (i: number) => left + i * step;
  const radius = (s: number) => 6 + s * 9;

  const keyed = (g: number) => (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect?.(g);
    }
  };

  const lastIndex = points.length - 1;
  return (
    <div ref={box} className="overflow-x-auto">
      <svg viewBox={`0 0 ${width} 150`} width={width} height={150} className="block" role="group"
           aria-label="Lineage: kept generations on the main line, discarded candidates branching off">
        <line x1={x(0)} x2={x(lastIndex)} y1={mainY} y2={mainY} stroke="var(--hema)" strokeWidth={2.5} />
        {growing && (
          <line x1={x(lastIndex)} x2={x(lastIndex) + step - 18} y1={mainY} y2={mainY} stroke="var(--hema)"
                strokeWidth={2.5} strokeDasharray="3 6" className="animate-pulse" />
        )}
        {points.map((p, i) => {
          const cx = x(i);
          const kept = p.accepted;
          const cy = kept ? mainY : branchY;
          const r = p.generation === 0 ? 8 : kept ? radius(p.score) : 7;
          const isSelected = selected === p.generation;
          const label = p.generation === 0
            ? `Generation 0, the undifferentiated stem, training score ${fmt(p.score)}`
            : `Generation ${p.generation}, ${kept ? "kept" : "discarded"}, training score ${fmt(p.score)}`;
          return (
            <g key={p.generation}>
              {!kept && (
                <path d={`M ${x(i - 1)} ${mainY} C ${x(i - 1) + step * 0.55} ${mainY}, ${cx - step * 0.35} ${branchY}, ${cx - r} ${branchY}`}
                      fill="none" stroke="var(--eosin)" strokeWidth={1.5} />
              )}
              <g role={onSelect ? "button" : undefined} tabIndex={onSelect ? 0 : undefined} aria-label={label}
                 aria-pressed={onSelect ? isSelected : undefined} onClick={() => onSelect?.(p.generation)}
                 onKeyDown={keyed(p.generation)} className={onSelect ? "cursor-pointer outline-none" : ""}>
                <title>{label}</title>
                <circle cx={cx} cy={cy} r={r + 8} fill="transparent" />
                {isSelected && <circle cx={cx} cy={cy} r={r + 5} fill="none" stroke="var(--ink)" strokeWidth={1.5} />}
                {p.generation === 0 ? (
                  <circle cx={cx} cy={cy} r={r} fill="var(--surface)" stroke="var(--hema)" strokeWidth={2.5} />
                ) : kept ? (
                  <circle cx={cx} cy={cy} r={r} fill={stain(p.score) === "var(--sunken)" ? "var(--surface)" : stain(p.score)}
                          stroke="var(--hema)" strokeWidth={p.score === 0 ? 2.5 : 0} />
                ) : (
                  <circle cx={cx} cy={cy} r={r} fill="var(--surface)" stroke="var(--eosin)" strokeWidth={2} />
                )}
                <text x={cx} y={cy - r - (isSelected ? 12 : 7)} textAnchor="middle" className="fill-ink text-[11px] tabular-nums">
                  {fmt(p.score)}
                </text>
                <text x={cx} y={140} textAnchor="middle"
                      className={`text-[11px] ${isSelected ? "fill-ink font-semibold" : "fill-muted"}`}>
                  {p.generation === 0 ? "stem" : `g${p.generation}`}
                </text>
              </g>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/** The same lineage, small enough for a table row. */
export function ScoreTrail({ points, growing = false }: { points: ScorePoint[]; growing?: boolean }) {
  const step = 14;
  const width = Math.max(points.length * step + (growing ? step : 0), step) + 6;
  const mainY = 15;
  return (
    <svg viewBox={`0 0 ${width} 22`} width={width} height={22} aria-hidden className="block">
      {points.length > 1 && (
        <line x1={7} x2={7 + (points.length - 1) * step} y1={mainY} y2={mainY} stroke="var(--line)" strokeWidth={1.5} />
      )}
      {points.map((p, i) => {
        const cx = 7 + i * step;
        return p.accepted ? (
          <circle key={p.generation} cx={cx} cy={mainY} r={2.5 + p.score * 3}
                  fill={p.score > 0 ? stain(p.score) : "var(--surface)"} stroke="var(--hema)" strokeWidth={p.score > 0 ? 0 : 1.5} />
        ) : (
          <circle key={p.generation} cx={cx} cy={5} r={2.5} fill="none" stroke="var(--eosin)" strokeWidth={1.3} />
        );
      })}
      {growing && <circle cx={7 + points.length * step} cy={mainY} r={2} fill="var(--hema)" className="animate-pulse" />}
    </svg>
  );
}
