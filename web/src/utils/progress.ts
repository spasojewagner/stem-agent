/** Reads the command line's output and says where a run is. The CLI prints
 * plain lines (see stem/evolve.py); this turns them into a status. */

export type Phase = "starting" | "baseline" | "development" | "scoring" | "waiting" | "done" | "stopped";

export interface GenerationResult {
  generation: number;
  kept: boolean;
  score: number;
}

export interface Progress {
  phase: Phase;
  generation: number | null;
  task: string | null;
  results: GenerationResult[];
  tasksScored: number;
  waiting: string | null;
  lastStep: string | null;
}

const STAMP = /^\d{2}:\d{2}:\d{2} /;

export function parseProgress(lines: string[]): Progress {
  const p: Progress = { phase: "starting", generation: null, task: null, results: [], tasksScored: 0,
    waiting: null, lastStep: null };
  for (const raw of lines) {
    const line = raw.replace(STAMP, "");
    const t = line.trim();
    let m: RegExpMatchArray | null;
    if ((m = t.match(/^generation (\d+): scoring the undifferentiated genome/))) {
      p.generation = Number(m[1]);
      p.phase = "baseline";
    } else if ((m = t.match(/^generation (\d+): (development|reusing)/))) {
      p.generation = Number(m[1]);
      p.phase = "development";
      p.task = null;
    } else if ((m = t.match(/^generation (\d+): scoring the candidate/))) {
      p.generation = Number(m[1]);
      p.phase = "scoring";
    } else if ((m = t.match(/^generation (\d+): (KEPT|discarded) \(training score ([\d.]+)/))) {
      p.results.push({ generation: Number(m[1]), kept: m[2] === "KEPT", score: Number(m[3]) });
      p.task = null;
    } else if ((m = t.match(/^task (\S+) \.\.\./))) {
      p.task = m[1];
      if (p.phase === "waiting") p.phase = p.generation === 0 ? "baseline" : "scoring";
    } else if (/^-> \S+: score /.test(t)) {
      p.tasksScored += 1;
    } else if ((m = t.match(/^\[(pace|429)\] (.*)$/))) {
      p.waiting = m[2];
    } else if ((m = t.match(/^step \d+: (.*)$/))) {
      p.lastStep = m[1];
      p.waiting = null;
    } else if (/^Stopped/.test(t)) {
      p.phase = "stopped";
    } else if (/^\| gen \| kept \|/.test(t) || /^genome: /.test(t)) {
      p.phase = "done";
    }
  }
  if (p.waiting && p.phase !== "done" && p.phase !== "stopped") {
    // a wait line only matters until the next sign of work
    const last = lines.length ? lines[lines.length - 1].replace(STAMP, "").trim() : "";
    if (!/^\[(pace|429)\]/.test(last)) p.waiting = null;
  }
  return p;
}
