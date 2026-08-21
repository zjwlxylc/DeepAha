import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "../app/page";


describe("DeepAha home", () => {
  it("presents the approved brand and current scope", () => {
    render(<Home />);

    expect(screen.getByRole("heading", { level: 1, name: "DeepAha" })).toBeVisible();
    expect(screen.getByText("Go Deep. Find the Aha.")).toBeVisible();
    expect(screen.getByText(/青年机会智能系统/)).toBeVisible();
    expect(screen.getByText(/工程基础建设/)).toBeVisible();
  });
});
