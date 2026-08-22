import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OpportunitiesPage from "../app/opportunities/page";
import { listPublicOpportunities } from "../lib/public-opportunities";
import { publicPage } from "./fixtures";

vi.mock("../lib/public-opportunities", async () => {
  const actual = await vi.importActual<typeof import("../lib/public-opportunities")>(
    "../lib/public-opportunities",
  );
  return { ...actual, listPublicOpportunities: vi.fn() };
});

const mockedList = vi.mocked(listPublicOpportunities);

describe("public opportunity directory", () => {
  beforeEach(() => {
    mockedList.mockReset();
    mockedList.mockResolvedValue(publicPage);
  });

  it("renders trusted fields, finite filters and fixture evidence boundary", async () => {
    render(
      await OpportunitiesPage({
        searchParams: Promise.resolve({
          q: "青年",
          type: "YOUTH_POLICY_BENEFIT",
          status: "OPEN",
          region: "合成浙江省",
          sort: "PUBLISHED_DESC",
        }),
      }),
    );

    expect(screen.getByRole("heading", { level: 1, name: "公开机会观测站" })).toBeVisible();
    expect(screen.getByRole("search")).toBeVisible();
    expect(screen.getByLabelText("搜索机会")).toHaveValue("青年");
    expect(screen.getByLabelText("机会类别")).toHaveValue("YOUTH_POLICY_BENEFIT");
    expect(screen.getByLabelText("当前状态")).toHaveValue("OPEN");
    expect(screen.getByLabelText("地域")).toHaveValue("合成浙江省");
    expect(screen.getByText(/固定合成许可安全夹具/)).toBeVisible();

    const card = screen.getByRole("article", { name: "合成青年人才补贴计划" });
    expect(within(card).getByText(publicPage.items[0].public_id)).toBeVisible();
    expect(within(card).getByText("合成浙江公共服务机构")).toBeVisible();
    expect(within(card).getByText(/2026-09-20/)).toBeVisible();
    expect(within(card).getByText(/2026-08-22/)).toBeVisible();
    expect(within(card).getByText(/截止时间已变化/)).toBeVisible();
    expect(screen.getByRole("link", { name: "下一页" })).toHaveAttribute(
      "href",
      expect.stringContaining("cursor=next-cursor"),
    );
  });

  it("renders an explicit empty state without turning it into an error", async () => {
    mockedList.mockResolvedValue({
      items: [],
      next_cursor: null,
      count: 0,
      data_labels: [],
      reproduced_at: null,
    });

    render(await OpportunitiesPage({ searchParams: Promise.resolve({ q: "不存在" }) }));

    expect(screen.getByRole("status")).toHaveTextContent("没有找到符合条件的公开机会");
    expect(screen.queryByText(/暂时无法加载/)).not.toBeInTheDocument();
  });

  it("never presents personal eligibility or marketing percentages", async () => {
    render(await OpportunitiesPage({ searchParams: Promise.resolve({}) }));

    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/ELIGIBLE|INELIGIBLE|匹配度|模型置信度|92%/i);
    expect(screen.getByRole("link", { name: "判断我是否适合" })).toHaveAttribute(
      "href",
      `/opportunities/${publicPage.items[0].public_id}/fit-check`,
    );
  });
});
