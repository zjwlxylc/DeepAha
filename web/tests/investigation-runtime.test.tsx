import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RuntimePanel from "../components/investigations/runtime-panel";
import { runtimeAction } from "../app/review/investigations/runtime-actions";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => undefined }) }));

describe("investigation readiness", () => {
  it("shows missing dependencies without declaring usable or running a task", () => {
    render(<RuntimePanel initial={{ login: "AUTHENTICATED", database: "CONNECTED", source_count: 0, worker: { state: "OFFLINE" }, wma: { state: "NOT_CONFIGURED", sdk_available: false }, dispatch_enabled: false }} />);
    expect(screen.getByText("未配置")).toBeInTheDocument();
    expect(screen.getByText(/暂无可用来源/)).toBeInTheDocument();
    expect(screen.getByText(/处理进程未运行/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /发起调查/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/模型名称/)).not.toBeInTheDocument();
  });
  it("missing cookie reports browser-specific recovery without returning secrets", async () => {
    const form = new FormData(); form.set("operation", "check");
    const result = await runtimeAction({ error: null }, form);
    expect(result.error).toContain("启动入口打开的浏览器");
  });
  it("announces readiness for dispatch only when everything is ready", () => {
    render(<RuntimePanel initial={{ login: "AUTHENTICATED", database: "CONNECTED", source_count: 3, worker: { state: "RUNNING" }, wma: { state: "CONNECTION_VERIFIED" }, dispatch_enabled: true }} />);
    expect(screen.getByTestId("dispatch-readiness")).toHaveTextContent(/已就绪/);
    expect(screen.getByTestId("dispatch-readiness")).toHaveTextContent(/发起调查/);
    // The panel never dispatches on its own and holds no per-task button.
    expect(screen.queryByRole("button", { name: /发起调查/ })).not.toBeInTheDocument();
  });
  it("explains an expired connection check without triggering a check on load", () => {
    render(<RuntimePanel initial={{ login: "AUTHENTICATED", database: "CONNECTED", source_count: 2, worker: { state: "RUNNING" }, wma: { state: "CHECK_EXPIRED" }, dispatch_enabled: false }} />);
    expect(screen.getByTestId("dispatch-readiness")).toHaveTextContent(/连接检查已过期/);
    expect(screen.getByTestId("wma-expired-note")).toBeVisible();
    expect(screen.queryByRole("button", { name: /发起调查/ })).not.toBeInTheDocument();
  });
});
