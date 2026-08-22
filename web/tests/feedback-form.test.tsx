import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import FeedbackForm from "../components/feedback-form";
import { personalDetail, personalPriorityPage, publicId } from "./personal-fixtures";

describe("feedback correction form", () => {
  it("uses controlled claims, bound versions, official evidence and explicit consent", () => {
    render(
      <FeedbackForm
        publicId={publicId}
        opportunityTitle={personalDetail.opportunity.title}
        rankingSnapshotId={personalPriorityPage.ranking_snapshot_id}
        matchSnapshotId={personalDetail.eligibility.snapshot_id}
        opportunityVersion={personalDetail.eligibility.opportunity_version}
        userStateVersion={1}
        evidence={personalDetail.opportunity.key_evidence}
      />,
    );

    expect(screen.getByLabelText("需要纠正什么")).toBeInstanceOf(HTMLSelectElement);
    expect(screen.getAllByRole("option")).toHaveLength(4);
    expect(screen.getByLabelText("补充说明（可跳过）")).toHaveAttribute("maxlength", "500");
    expect(screen.getByText(/不要填写身份证号、手机号、邮箱或其他敏感个人信息/)).toBeVisible();
    expect(
      (screen.getByRole("checkbox", { name: /官方证据/ }) as HTMLInputElement).value,
    ).toBe(personalDetail.opportunity.key_evidence[0].evidence_ref_id);
    expect(screen.getByRole("checkbox", { name: /同意仅用于反馈审核与验证/ })).toBeRequired();
    expect(screen.getByRole("button", { name: "提交纠错" })).toBeVisible();
    expect(document.body.textContent).not.toMatch(/owner_user_id|reviewer_id|置信度|匹配度/);
  });
});
