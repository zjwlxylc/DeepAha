import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ReviewBrowser from "../components/investigations/review-browser";

describe("review browser", () => {
  const rows = Array.from({ length: 27 }, (_, index) => ({ id: index, name: `岗位 ${index}`, attention: index === 26 }));
  function setup() {
    render(<ReviewBrowser items={rows} label="岗位核对" searchText={row => row.name} needsAttention={row => row.attention}>
      {visible => <ul>{visible.map(row => <li key={row.id}>{row.name}</li>)}</ul>}
    </ReviewBrowser>);
  }
  it("bounds the visible workload and keeps every later row reachable", () => {
    setup();
    expect(screen.getAllByRole("listitem")).toHaveLength(12);
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    expect(screen.getByText("岗位 12")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    expect(screen.getByText("岗位 26")).toBeVisible();
    expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
  });
  it("finds uncertain rows outside the current page and resets pagination on filtering", () => {
    setup();
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    fireEvent.click(screen.getByRole("button", { name: "优先看待处理 1" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByText("岗位 26")).toBeVisible();
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索岗位核对" }), { target: { value: "不存在" } });
    expect(screen.getByText("没有找到相符内容。可以更换关键词，或查看全部。" )).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "清除筛选" }));
    expect(screen.getByText("岗位 0")).toBeVisible();
  });
});
