import { screen } from "@testing-library/react";

import { exchangeRun } from "../test/fixtures";
import { mockApi, renderAt } from "../test/render";
import { RunsPage } from "./RunsPage";

describe("RunsPage", () => {
  it("lists runs with their progress from the undifferentiated score to the best", async () => {
    mockApi({ "GET /api/runs": [exchangeRun] });
    renderAt(<RunsPage />);
    const link = await screen.findByRole("link", { name: "exchange-1" });
    expect(link).toHaveAttribute("href", "/runs/exchange-1");
    expect(screen.getByText("2 kept of 3")).toBeInTheDocument();
    expect(screen.getByText("0.71")).toBeInTheDocument();
    expect(screen.getByText("182K")).toBeInTheDocument();
    expect(screen.getByText("2 min ago")).toBeInTheDocument();
  });

  it("says how to get started when there are no runs", async () => {
    mockApi({ "GET /api/runs": [] });
    renderAt(<RunsPage />);
    expect(await screen.findByText("No runs yet")).toBeInTheDocument();
    expect(screen.getByText("python -m studio.demo")).toBeInTheDocument();
  });

  it("shows the API's error", async () => {
    mockApi({});
    renderAt(<RunsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("no mock for GET /api/runs");
  });
});
