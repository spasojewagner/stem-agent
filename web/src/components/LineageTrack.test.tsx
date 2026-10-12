import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { exchangeRun } from "../test/fixtures";
import { LineageTrack } from "./LineageTrack";

describe("LineageTrack", () => {
  it("labels every generation with its fate and score", () => {
    render(<LineageTrack points={exchangeRun.scores} onSelect={() => {}} />);
    expect(screen.getByRole("button", { name: /Generation 0, the undifferentiated stem/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generation 2, kept, training score 0.71" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generation 3, discarded, training score 0.64" })).toBeInTheDocument();
  });

  it("selects a generation by click or keyboard", async () => {
    const onSelect = vi.fn();
    render(<LineageTrack points={exchangeRun.scores} selected={2} onSelect={onSelect} />);
    expect(screen.getByRole("button", { name: /Generation 2,/ })).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(screen.getByRole("button", { name: /Generation 3,/ }));
    expect(onSelect).toHaveBeenLastCalledWith(3);

    screen.getByRole("button", { name: /Generation 1,/ }).focus();
    await userEvent.keyboard("{Enter}");
    expect(onSelect).toHaveBeenLastCalledWith(1);
  });
});
