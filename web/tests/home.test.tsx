import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "../app/page";
import SiteHeader from "../components/site-header";


describe("DeepAha home", () => {
  it("presents the approved brand and public trust scope", () => {
    render(
      <>
        <SiteHeader />
        <Home />
      </>,
    );

    expect(screen.getByLabelText("DeepAha 首页")).toHaveTextContent("DeepAha");
    expect(screen.getByText("Go Deep. Find the Aha.")).toBeVisible();
    expect(screen.getByText(/青年机会智能系统/)).toBeVisible();
    expect(screen.getByRole("heading", { level: 1, name: /公开机会观测站/ })).toBeVisible();
    expect(screen.getByRole("link", { name: /浏览公开机会/ })).toHaveAttribute(
      "href",
      "/opportunities",
    );
    expect(screen.queryByText(/匹配度|个人资格|92%/)).not.toBeInTheDocument();
  });
});
