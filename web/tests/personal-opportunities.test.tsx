import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PersonalOpportunitiesPage from "../app/me/opportunities/page";
import { getPersonalPriorities } from "../lib/personal-opportunities";
import { personalPriorityPage } from "./personal-fixtures";

vi.mock("../lib/personal-opportunities", async () => {
  const actual = await vi.importActual<typeof import("../lib/personal-opportunities")>(
    "../lib/personal-opportunities",
  );
  return { ...actual, getPersonalPriorities: vi.fn() };
});

const mockedPriorities = vi.mocked(getPersonalPriorities);

describe("personal opportunity priorities", () => {
  beforeEach(() => {
    mockedPriorities.mockReset();
    mockedPriorities.mockResolvedValue(personalPriorityPage);
  });

  it("shows no more than three deterministic priorities and their reasons", async () => {
    render(await PersonalOpportunitiesPage());

    expect(screen.getByRole("heading", { level: 1, name: "未来 90 天行动台" })).toBeVisible();
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(screen.getByText("资格条件已满足")).toBeVisible();
    expect(screen.getByText(/合成许可安全夹具/)).toBeVisible();
    expect(document.body.textContent).not.toMatch(/匹配度|置信度|\d+%/);
  });

  it("renders a useful empty state", async () => {
    mockedPriorities.mockResolvedValue({ ...personalPriorityPage, items: [] });

    render(await PersonalOpportunitiesPage());

    expect(screen.getByRole("status")).toHaveTextContent("暂时没有需要优先处理的机会");
  });
});
