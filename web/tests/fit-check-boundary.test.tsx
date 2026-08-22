import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import FitCheckBoundaryPage from "../app/opportunities/[publicId]/fit-check/page";
import { publicId } from "./fixtures";


describe("Phase 6 fit-check boundary", () => {
  it("is honest, static and collects no profile", async () => {
    render(await FitCheckBoundaryPage({ params: Promise.resolve({ publicId }) }));

    expect(screen.getByRole("heading", { level: 1, name: "个人判断尚未开放" })).toBeVisible();
    expect(screen.getByText(/Phase 6/)).toBeVisible();
    expect(screen.getByText(/不会收集你的画像，也不会计算个人资格/)).toBeVisible();
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/ELIGIBLE|INELIGIBLE|匹配度|%/i)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回机会详情" })).toHaveAttribute(
      "href",
      `/opportunities/${publicId}`,
    );
  });
});
