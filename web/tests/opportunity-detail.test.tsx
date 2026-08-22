import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OpportunityDetailPage from "../app/opportunities/[publicId]/page";
import { getPublicOpportunity } from "../lib/public-opportunities";
import { publicDetail, publicId } from "./fixtures";

vi.mock("../lib/public-opportunities", async () => {
  const actual = await vi.importActual<typeof import("../lib/public-opportunities")>(
    "../lib/public-opportunities",
  );
  return { ...actual, getPublicOpportunity: vi.fn() };
});

const mockedDetail = vi.mocked(getPublicOpportunity);

describe("public opportunity detail", () => {
  beforeEach(() => {
    mockedDetail.mockReset();
    mockedDetail.mockResolvedValue(publicDetail);
  });

  it("renders official links, evidence locator and change history", async () => {
    render(await OpportunityDetailPage({ params: Promise.resolve({ publicId }) }));

    expect(screen.getByRole("heading", { level: 1, name: publicDetail.title })).toBeVisible();
    expect(screen.getByText(publicId)).toBeVisible();
    expect(screen.getByText(/固定合成许可安全夹具/)).toBeVisible();

    const official = screen.getByRole("link", { name: "打开官方入口" });
    expect(official).toHaveAttribute("href", publicDetail.application_url);
    expect(official).toHaveAttribute("target", "_blank");
    expect(official).toHaveAttribute("rel", "noreferrer");

    const evidence = screen.getByRole("article", { name: /application_url/ });
    expect(within(evidence).getByText(/EvidenceRef/)).toHaveTextContent(
      publicDetail.key_evidence[0].evidence_ref_id,
    );
    expect(within(evidence).getByText(/main article/)).toBeVisible();
    expect(within(evidence).getByRole("link", { name: "查看官方证据" })).toHaveAttribute(
      "href",
      publicDetail.key_evidence[0].official_url,
    );

    const timeline = screen.getByRole("list", { name: "机会变化历史" });
    expect(within(timeline).getByText(/截止时间已变化/)).toBeVisible();
    expect(within(timeline).getByText(/2026-09-10/)).toBeVisible();
    expect(within(timeline).getByText(/2026-09-20/)).toBeVisible();
  });
});
