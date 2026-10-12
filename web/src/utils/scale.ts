/** Score in [0, 1] -> a fill on the hematoxylin ramp (stronger stain = higher score). */
export function stain(score: number): string {
  const s = Math.max(0, Math.min(1, score));
  if (s === 0) return "var(--sunken)";
  return `color-mix(in oklab, var(--hema) ${Math.round(18 + s * 82)}%, var(--surface))`;
}

export function stainText(score: number): string {
  return score >= 0.55 ? "var(--surface)" : "var(--ink)";
}
