import { parseProgress } from "./progress";

const growLog = [
  "10:00:01 generation 0: scoring the undifferentiated genome on archive training tasks",
  "10:00:01   task ar-train-1 ...",
  "10:00:09   -> ar-train-1: score 0.00 (answered None, expected 762.6 -> wrong)",
  "10:00:10 ",
  "10:00:10 generation 1: development",
  "10:00:14   step 1: probe -> {'documents': [...]} ",
  "10:00:20   step 2: write_tool -> wrote tool answer_question",
  "10:00:31 development summary: Wrote answer_question.",
  "10:00:31 generation 1: scoring the candidate on training tasks",
  "10:00:31   task ar-train-1 ...",
  "10:00:40   -> ar-train-1: score 1.00 (answered 762.6, expected 762.6 -> correct)",
  "10:00:40 generation 1: KEPT (training score 1.00)",
  "10:00:41 generation 2: development",
  "10:00:45 [pace] openai/gpt-oss-120b: waiting 21s for the per-minute token limit",
];

describe("parseProgress", () => {
  it("follows generations, tasks and results", () => {
    const p = parseProgress(growLog);
    expect(p.generation).toBe(2);
    expect(p.phase).toBe("development");
    expect(p.results).toEqual([{ generation: 1, kept: true, score: 1 }]);
    expect(p.tasksScored).toBe(2);
    expect(p.lastStep).toBe("write_tool -> wrote tool answer_question");
  });

  it("reports a rate-limit wait only while it is the latest news", () => {
    expect(parseProgress(growLog).waiting).toMatch(/waiting 21s/);
    const after = [...growLog, "10:01:07   step 1: view_genome -> identity: ..."];
    expect(parseProgress(after).waiting).toBeNull();
  });

  it("recognises discarded candidates, the end and a stop", () => {
    const p = parseProgress([
      "generation 3: discarded (training score 0.64, best 0.71)",
      "| gen | kept | train score | tokens | summary |",
    ]);
    expect(p.results).toEqual([{ generation: 3, kept: false, score: 0.64 }]);
    expect(p.phase).toBe("done");
    expect(parseProgress(["Stopped with Ctrl+C. Finished generations ..."]).phase).toBe("stopped");
  });

  it("starts out knowing nothing", () => {
    expect(parseProgress([])).toMatchObject({ phase: "starting", generation: null, results: [] });
  });
});
