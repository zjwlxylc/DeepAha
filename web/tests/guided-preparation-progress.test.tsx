import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PreparationProgress } from "../components/investigations/guided-prepare";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
afterEach(() => vi.useRealTimers());

it("shows elapsed waiting without inventing progress and offers a read-only reload", () => {
  vi.useFakeTimers();
  const { unmount } = render(<PreparationProgress />);
  expect(screen.getByRole("status")).toHaveTextContent("正在等待准备结果");
  act(() => vi.advanceTimersByTime(106000));
  expect(screen.getByText(/已等待 106 秒/)).toBeVisible();
  expect(screen.getByRole("button", { name: "重新读取已保存结果" })).toHaveAttribute("type", "button");
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  unmount();
  expect(vi.getTimerCount()).toBe(0);
});
