import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import OpportunityDetailError from "../app/opportunities/[publicId]/error";
import OpportunityDetailLoading from "../app/opportunities/[publicId]/loading";
import OpportunitiesError from "../app/opportunities/error";
import OpportunitiesLoading from "../app/opportunities/loading";


describe("public trust route states", () => {
  it("shows distinct loading states", () => {
    const { rerender } = render(<OpportunitiesLoading />);
    expect(screen.getByRole("status")).toHaveTextContent("正在加载公开机会");

    rerender(<OpportunityDetailLoading />);
    expect(screen.getByRole("status")).toHaveTextContent("正在核对机会详情");
  });

  it("shows explicit retryable errors without leaking exception text", () => {
    const reset = vi.fn();
    const error = new Error("database password should never render");
    const { rerender } = render(<OpportunitiesError error={error} reset={reset} />);
    expect(screen.getByRole("alert")).toHaveTextContent("暂时无法加载公开机会");
    expect(screen.queryByText(/database password/)).not.toBeInTheDocument();

    rerender(<OpportunityDetailError error={error} reset={reset} />);
    expect(screen.getByRole("alert")).toHaveTextContent("暂时无法核对机会详情");
    expect(screen.queryByText(/database password/)).not.toBeInTheDocument();
  });
});
