import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "../app/review/investigations/[taskId]/materials/[artifactId]/route";
import { taskId } from "./investigations-fixture";

const cookieGet = vi.fn();
vi.mock("next/headers", () => ({ cookies: async () => ({ get: cookieGet }) }));
const context = { params: Promise.resolve({ taskId, artifactId: "attachment-1" }) };
describe("protected investigation downloads", () => {
  beforeEach(() => { vi.restoreAllMocks(); cookieGet.mockReturnValue({ value: "synthetic-reviewer-session" }); });
  it("streams bytes as a private attachment and keeps the bearer token server-side", async () => {
    const upstream = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("official bytes", { headers: {
      "Content-Type": "text/html", "Content-Disposition": "inline", "Set-Cookie": "upstream=private", "Authorization": "must-not-leak",
    } }));
    const response = await GET(new Request("http://localhost/download"), context);
    expect(await response.text()).toBe("official bytes");
    expect(response.headers.get("Content-Disposition")).toBe('attachment; filename="original.bin"');
    expect(response.headers.get("Cache-Control")).toContain("no-store");
    expect(response.headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect(response.headers.get("Set-Cookie")).toBeNull();
    expect(response.headers.get("Authorization")).toBeNull();
    expect(new Headers(upstream.mock.calls[0][1]?.headers).get("Authorization")).toBe("Bearer synthetic-reviewer-session");
    expect(upstream.mock.calls[0][1]?.redirect).toBe("error");
  });
  it.each(["pdf", "doc", "docx", "xls", "xlsx", "html", "txt", "png", "jpg", "bin"])("preserves only the safe backend filename with %s extension", async (extension) => {
    const filename = `original-0123456789abcdef.${extension}`;
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("bytes", { headers: {
      "Content-Disposition": `attachment; filename="${filename}"`,
    } }));
    const response = await GET(new Request("http://localhost/download"), context);
    expect(response.headers.get("Content-Disposition")).toBe(`attachment; filename="${filename}"`);
  });
  it.each([
    'inline; filename="original-0123456789abcdef.pdf"',
    'attachment; filename="../../original-0123456789abcdef.pdf"',
    'attachment; filename="original-0123456789abcdef.exe"',
    'attachment; filename="original-0123456789abcdef.pdf"; filename*=UTF-8\'\'evil.exe',
    'attachment; filename="original-0123456789ABCDEF.pdf"',
    'attachment; filename="original-0123456789abcdef0.pdf"',
  ])("falls back for an untrusted disposition: %s", async (disposition) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("bytes", { headers: { "Content-Disposition": disposition } }));
    const response = await GET(new Request("http://localhost/download"), context);
    expect(response.headers.get("Content-Disposition")).toBe('attachment; filename="original.bin"');
  });
  it("rejects missing authentication without touching the API", async () => {
    cookieGet.mockReturnValue(undefined); const upstream = vi.spyOn(globalThis, "fetch");
    expect((await GET(new Request("http://localhost/download"), context)).status).toBe(401);
    expect(upstream).not.toHaveBeenCalled();
  });
  it("does not return an upstream error body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("private-upstream-secret", { status: 403 }));
    const response = await GET(new Request("http://localhost/download"), context);
    expect(response.status).toBe(403);
    expect(await response.text()).not.toContain("private-upstream-secret");
  });
});
