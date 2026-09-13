import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import GuidedIdentity from "../components/investigations/guided-identity";
import GuidedExisting from "../components/investigations/guided-existing";
import { task, bindingTarget, ruleReadyTask } from "./investigations-fixture";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

it("offers an explicit existing announcement route instead of another blind create", () => {
  const t = structuredClone(task);
  t.binding_entities!.push({ id: "position-2", name: "第二岗位", code: "P002", kind: "position" });
  const target = { ...bindingTarget, title: String(t.opportunities!.opportunity_name) };
  render(<GuidedIdentity task={t} ids={["position-1", "position-2"]} requestKey="key" targets={[target]} />);
  expect(screen.getByText("系统中已有同名公告，请先核对是否为同一份")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "查看已有公告并继续" }));
  expect(screen.getByLabelText("选择已有公告")).toHaveValue("");
  expect(screen.getByRole("button", { name: "确认使用已有记录，继续" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("选择已有公告"), { target: { value: `${target.opportunity_id}/${target.version}` } });
  expect(screen.getByLabelText(/教学岗位.*对应哪条已有岗位/)).toHaveValue("");
  expect(screen.getByLabelText(/第二岗位.*对应哪条已有岗位/)).toHaveValue("");
  expect(screen.getByRole("button", { name: "确认使用已有记录，继续" })).toBeDisabled();
});

it("preserves prior position mappings and restricts later additions to the bound announcement", () => {
  const t = ruleReadyTask();
  t.entity_binding!.positions = [{ entity_id: "prior-position", opportunity_unit_id: bindingTarget.positions[0].unit_id, opportunity_unit_version_id: bindingTarget.positions[0].version_id }];
  render(<GuidedExisting task={t} ids={["position-1"]} requestKey="key" targets={[bindingTarget, { ...bindingTarget, opportunity_id: "other", title: "另一份公告" }]} />);
  expect(document.querySelector('input[name="position:prior-position"]')).toHaveValue(`${bindingTarget.positions[0].unit_id}/${bindingTarget.positions[0].version_id}`);
  expect(screen.queryByRole("option", { name: /另一份公告/ })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("选择已有公告"), { target: { value: `${bindingTarget.opportunity_id}/1` } });
  expect(screen.queryByRole("option", { name: /示例教学岗位/ })).not.toBeInTheDocument();
});

it("does not suggest creating duplicates when a conflicting record cannot be listed", () => {
  render(<GuidedExisting task={task} ids={["position-1"]} requestKey="key" targets={[]} />);
  expect(screen.getByRole("alert")).toHaveTextContent("反复点击新建不能解决此问题");
  expect(screen.queryByRole("button", { name: "确认使用已有记录，继续" })).not.toBeInTheDocument();
});
