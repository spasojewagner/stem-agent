import { ago, duration, score, tokens } from "./format";

describe("format", () => {
  it("scores and token counts", () => {
    expect(score(0.7115)).toBe("0.71");
    expect(score(null)).toBe("–");
    expect(tokens(950)).toBe("950");
    expect(tokens(1500)).toBe("1.5K");
    expect(tokens(182_400)).toBe("182K");
    expect(tokens(2_300_000)).toBe("2.3M");
  });

  it("durations and relative times", () => {
    expect(duration(42)).toBe("42 s");
    expect(duration(125)).toBe("2 min 5 s");
    expect(duration(3 * 3600 + 120)).toBe("3 h 2 min");
    const now = Date.parse("2026-10-12T12:00:00Z");
    expect(ago(now / 1000 - 30, now)).toBe("just now");
    expect(ago(now / 1000 - 600, now)).toBe("10 min ago");
    expect(ago(now / 1000 - 86400 * 3, now)).toBe("3 days ago");
  });
});
