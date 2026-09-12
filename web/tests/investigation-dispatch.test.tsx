import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DispatchButton from "../components/investigations/dispatch-button";
import { requestInvestigationDispatchAction } from "../app/review/investigations/actions";
import { task as fixture, taskId } from "./investigations-fixture";

vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => ({ value: "synthetic-reviewer-session" }) }) }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

const empty = { error: null, message: null, taskId: null };
const requestKey = "11111111-1111-4111-8111-111111111111";

function dispatchForm() {
  const data = new FormData();
  data.set("task_id", taskId);
  data.set("request_key", requestKey);
  return data;
}

describe("investigation dispatch control", () => {
  it("hides the dispatch control while the system is not ready", () => {
    render(<DispatchButton task={{ task_id: taskId, status: "QUEUED", dispatch_requested_at: null }} dispatchEnabled={false} requestKey={requestKey} />);
    expect(screen.queryByRole("button", { name: /发起调查/ })).not.toBeInTheDocument();
  });

  it("enables dispatch for a queued task once the system is ready", () => {
    render(<DispatchButton task={{ task_id: taskId, status: "QUEUED", dispatch_requested_at: null }} dispatchEnabled requestKey={requestKey} />);
    expect(screen.getByRole("button", { name: "发起调查" })).toBeEnabled();
  });

  it("offers download-only recovery for a finished failed attempt with remote identifiers", () => {
    render(<DispatchButton task={{ task_id: taskId, status: "COLLECTION_RETRYABLE", dispatch_requested_at: "2026-09-12T00:00:00Z", dispatch_pending: false, runtime_id: "runtime", remote_session_id: "session" }} dispatchEnabled requestKey={requestKey} />);
    expect(screen.getByRole("button", { name: "恢复材料" })).toBeEnabled();
  });

  it("cannot recover without remote identifiers", () => {
    render(<DispatchButton task={{ task_id: taskId, status: "EXECUTION_UNCERTAIN", dispatch_requested_at: null }} dispatchEnabled requestKey={requestKey} />);
    expect(screen.getByRole("button", { name: /恢复材料/ })).toBeDisabled();
    expect(screen.getByText(/缺少可恢复的远端会话/)).toBeVisible();
  });

  it.each(["PENDING_REVIEW", "APPROVED", "FAILED_VALIDATION"])("shows a disabled reason for a non-queued task (%s)", (status) => {
    render(<DispatchButton task={{ task_id: taskId, status, dispatch_requested_at: null }} dispatchEnabled requestKey={requestKey} />);
    expect(screen.getByRole("button", { name: /发起调查/ })).toBeDisabled();
    expect(screen.getByText(/本任务不在可发起状态/)).toBeVisible();
  });

  it("stops re-dispatch once an intent already exists", () => {
    render(<DispatchButton task={{ task_id: taskId, status: "QUEUED", dispatch_requested_at: "2026-09-11T02:00:00Z" }} dispatchEnabled requestKey={requestKey} />);
    expect(screen.getByRole("button", { name: /发起调查/ })).toBeDisabled();
    expect(screen.getByText(/已发起/)).toBeVisible();
  });
});

describe("requestInvestigationDispatchAction", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  const submissions = () => vi.mocked(fetch).mock.calls.filter(([, request]) => request?.method === "POST");

  it("posts to the dispatch endpoint with a derived idempotency key", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(fixture));
    const result = await requestInvestigationDispatchAction(empty, dispatchForm());
    expect(result.taskId).toBe(taskId);
    expect(result.message).toMatch(/已发起调查/);
    const [path, request] = submissions()[0];
    expect(String(path)).toBe(`http://127.0.0.1:8000/api/v1/local-human-test/investigation-runtime/tasks/${taskId}/dispatch`);
    expect(new Headers(request?.headers).get("Idempotency-Key")).toBeTruthy();
    expect(JSON.parse(String(request?.body))).toEqual({});
  });

  it("replays the same derived key after a lost receipt without a second write identity", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new TypeError("synthetic lost receipt")).mockResolvedValue(Response.json(fixture));
    expect((await requestInvestigationDispatchAction(empty, dispatchForm())).error).toBeTruthy();
    expect((await requestInvestigationDispatchAction(empty, dispatchForm())).taskId).toBe(taskId);
    const keys = submissions().map(([, request]) => new Headers(request?.headers).get("Idempotency-Key"));
    expect(keys[0]).toBeTruthy();
    expect(keys[0]).toBe(keys[1]);
  });

  it("requires the form identity and a valid task id before any request", async () => {
    vi.spyOn(globalThis, "fetch");
    const missingKey = dispatchForm(); missingKey.delete("request_key");
    expect((await requestInvestigationDispatchAction(empty, missingKey)).error).toBeTruthy();
    const badTask = dispatchForm(); badTask.set("task_id", "not-a-uuid");
    expect((await requestInvestigationDispatchAction(empty, badTask)).error).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each([401, 403])("shows the shared login help on %s without leaking upstream detail", async (status) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status }));
    const result = await requestInvestigationDispatchAction(empty, dispatchForm());
    expect(result.error).toMatch(/启动入口打开的浏览器/);
  });

  it.each([
    ["TASK_NOT_DISPATCHABLE", /不在可发起状态/],
    ["TASK_ALREADY_RUNNING", /执行中的租约|无需重复发起/],
    ["UNKNOWN_PRIVATE_REASON", /刷新/],
  ])("explains dispatch conflict %s without leaking raw codes", async (code, expected) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ detail: { code, private_value: "private-upstream-secret" } }, { status: 409 }));
    const result = await requestInvestigationDispatchAction(empty, dispatchForm());
    expect(result.error).toMatch(expected);
    expect(result.error).not.toMatch(/private-upstream-secret|UNKNOWN_PRIVATE_REASON/);
  });
});
