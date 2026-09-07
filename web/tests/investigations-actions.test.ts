import { beforeEach, describe, expect, it, vi } from "vitest";

import { createInvestigationAction, reviewInvestigationAction } from "../app/review/investigations/actions";
import { source, task, taskId } from "./investigations-fixture";

vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => ({ value: "synthetic-reviewer-session" }) }) }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

const empty = { error: null, message: null, taskId: null };
function creation() {
  const data = new FormData();
  data.set("source_key", `${source.source_id}/${source.endpoint_id}`);
  data.set("notice_url", task.notice_url);
  data.set("brief", task.brief);
  data.set("wall_time_seconds", "600");
  data.set("expected_artifact_urls", `${source.url}/jobs.xlsx\n`);
  data.set("expected_entity_keys", "P001\nP002");
  data.set("calibration", "on");
  return data;
}

describe("investigation actions", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => Response.json(
      String(url).endsWith("/sources") ? { sources: [source] } : task,
    ));
  });
  const submissions = () => vi.mocked(fetch).mock.calls.filter(([, request]) => request?.method === "POST");

  it("registers a bounded task without an execution request", async () => {
    const result = await createInvestigationAction(empty, creation());
    expect(result.taskId).toBe(taskId);
    expect(submissions()).toHaveLength(1);
    const [path, request] = submissions()[0];
    expect(String(path)).toMatch(/\/api\/v1\/local-human-test\/investigations$/);
    expect(JSON.parse(String(request?.body))).toEqual({ source_id: source.source_id,
      endpoint_id: source.endpoint_id, notice_url: task.notice_url, brief: task.brief,
      expected_artifact_urls: [`${source.url}/jobs.xlsx`], expected_entity_keys: ["P001", "P002"],
      calibration: true, wall_time_seconds: 600 });
    expect(new Headers(request?.headers).get("Idempotency-Key")).toBeTruthy();
  });

  it.each(["59", "1801", "60.5"])("rejects invalid execution bound %s before registration", async (limit) => {
    const data = creation(); data.set("wall_time_seconds", limit);
    expect((await createInvestigationAction(empty, data)).error).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each([
    "http://official.example.gov.cn/1", "https://official.example.gov.cn:8443/1",
    "https://official.example.gov.cn:80/1", "https://official.example.gov.cn/one\\two",
    "https:official.example.gov.cn/1", "https:///official.example.gov.cn/1",
  ])("rejects an unsupported URL before registration: %s", async (url) => {
    const data = creation(); data.set("notice_url", url);
    expect((await createInvestigationAction(empty, data)).error).toMatch(/HTTPS/);
    expect(submissions()).toHaveLength(0);
  });

  it.each(["notice_url", "expected_artifact_urls"])("checks %s against the selected source hosts", async (field) => {
    const data = creation(); data.set(field, "https://other.example.gov.cn/1");
    expect((await createInvestigationAction(empty, data)).error).toMatch(/所选来源.*域名/);
    expect(submissions()).toHaveLength(0);
  });

  it("allows explicit HTTPS port 443 and validates the selected source again", async () => {
    const data = creation(); data.set("notice_url", "https://official.example.gov.cn:443/1");
    expect((await createInvestigationAction(empty, data)).taskId).toBe(taskId);
    vi.mocked(fetch).mockClear();
    vi.mocked(fetch).mockResolvedValue(Response.json({ sources: [] }));
    expect((await createInvestigationAction(empty, creation())).error).toMatch(/来源.*批准|已批准.*来源/);
    expect(submissions()).toHaveLength(0);
  });

  it.each([
    ["APPROVED_SOURCE_REQUIRED", /来源.*批准|已批准.*来源/],
    ["NOTICE_OUTSIDE_APPROVED_HOSTS", /所选来源.*域名/],
    ["IDEMPOTENCY_CONFLICT", /登记请求.*重复|重复.*登记/],
    ["UNKNOWN_PRIVATE_BACKEND_REASON", /登记未完成/],
  ])("explains registration conflict %s without exposing raw details", async (code, expected) => {
    vi.mocked(fetch).mockImplementation(async (url) => String(url).endsWith("/sources")
      ? Response.json({ sources: [source] })
      : Response.json({ detail: { code, private_value: "private-upstream-secret" } }, { status: 409 }));
    const result = await createInvestigationAction(empty, creation());
    expect(result.error).toMatch(expected);
    expect(result.error).not.toMatch(/材料版本|private-upstream-secret|UNKNOWN_PRIVATE/);
  });

  it("rejects credential-bearing URLs and hides upstream failures", async () => {
    const data = creation(); data.set("notice_url", "https://user:secret@official.example.gov.cn/1");
    expect((await createInvestigationAction(empty, data)).error).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
    vi.mocked(fetch).mockRejectedValue(new Error("private-upstream-secret"));
    const result = await createInvestigationAction(empty, creation());
    expect(result.error).toBeTruthy();
    expect(JSON.stringify(result)).not.toContain("private-upstream-secret");
  });

  it("binds explicit review to the delivered material version", async () => {
    const data = new FormData();
    data.set("task_id", taskId); data.set("delivery_hash", task.delivery_hash!);
    data.set("decision", "APPROVE"); data.set("reason", "已逐项核对官方原件和对应实体");
    const result = await reviewInvestigationAction(empty, data);
    expect(result.message).toMatch(/内部材料审核/);
    const [path, request] = submissions()[0];
    expect(String(path)).toMatch(new RegExp(`/investigations/${taskId}/review$`));
    expect(JSON.parse(String(request?.body))).toEqual({ decision: "APPROVE", delivery_hash: task.delivery_hash, reason: "已逐项核对官方原件和对应实体" });
    vi.clearAllMocks(); data.delete("delivery_hash");
    expect((await reviewInvestigationAction(empty, data)).error).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });
});
