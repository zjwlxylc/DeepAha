import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PersonalDetailError from "../app/me/opportunities/[publicId]/error";
import PersonalDetailLoading from "../app/me/opportunities/[publicId]/loading";
import FeedbackError from "../app/me/opportunities/[publicId]/feedback/error";
import FeedbackLoading from "../app/me/opportunities/[publicId]/feedback/loading";
import FeedbackDetailError from "../app/me/feedback/[feedbackId]/error";
import FeedbackDetailLoading from "../app/me/feedback/[feedbackId]/loading";
import FeedbackListError from "../app/me/feedback/error";
import FeedbackListLoading from "../app/me/feedback/loading";
import PersonalOpportunitiesError from "../app/me/opportunities/error";
import PersonalOpportunitiesLoading from "../app/me/opportunities/loading";
import ProfileError from "../app/profile/error";
import ProfileLoading from "../app/profile/loading";

const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

describe("personal route states", () => {
  it.each([
    [ProfileLoading, "正在读取你的最小画像"],
    [PersonalOpportunitiesLoading, "正在重放个人判断"],
    [PersonalDetailLoading, "正在读取个人解释"],
    [FeedbackLoading, "正在核对纠错上下文"],
    [FeedbackListLoading, "正在读取纠错状态"],
    [FeedbackDetailLoading, "正在读取处理详情"],
  ])("renders an announced loading state", (LoadingState, heading) => {
    render(<LoadingState />);

    expect(screen.getByRole("status")).toBeVisible();
    expect(screen.getByRole("heading", { name: heading })).toBeVisible();
  });

  it.each([
    [ProfileError, "画像暂时无法读取", "重试"],
    [PersonalOpportunitiesError, "个人行动台暂时不可用", "重新加载"],
    [PersonalDetailError, "个人解释暂时无法读取", "重试"],
    [FeedbackError, "纠错上下文暂时不可用", "重试"],
    [FeedbackListError, "纠错状态暂时无法读取", "重试"],
    [FeedbackDetailError, "处理详情不可用", "重试"],
  ])("renders an explicit recoverable error", (ErrorState, heading, buttonName) => {
    refresh.mockClear();
    const reset = vi.fn();
    render(<ErrorState reset={reset} />);

    expect(screen.getByRole("alert")).toBeVisible();
    expect(screen.getByRole("heading", { name: heading })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: buttonName }));
    expect(reset).toHaveBeenCalledOnce();
    expect(refresh).toHaveBeenCalledOnce();
  });
});
