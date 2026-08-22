import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import FitCheckBoundaryPage from "../app/opportunities/[publicId]/fit-check/page";
import { publicId } from "./fixtures";


describe("Phase 6 fit-check boundary", () => {
  it("opens the controlled progressive-profile entry without a fake result", async () => {
    render(await FitCheckBoundaryPage({ params: Promise.resolve({ publicId }) }));

    expect(screen.getByRole("heading", { level: 1, name: "先完成最小画像" })).toBeVisible();
    expect(screen.getByText(/缺失信息会保留为未知/)).toBeVisible();
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/ELIGIBLE|INELIGIBLE|匹配度|%/i)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "填写最小画像" })).toHaveAttribute(
      "href",
      `/profile?returnTo=/me/opportunities/${publicId}`,
    );
  });
});
