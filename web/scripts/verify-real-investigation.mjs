// Explicit, bounded live acceptance through the real launcher-owned UI only.
// A persisted receipt prevents this verifier from silently registering a second task.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { expect } from "@playwright/test";

export async function verifyRealInvestigation(page, readyPath) {
  const directory = dirname(readyPath);
  const receiptPath = join(directory, "real-investigation-acceptance.json");
  const origin = new URL(page.url()).origin;
  let receipt = existsSync(receiptPath) ? JSON.parse(readFileSync(receiptPath, "utf8")) : { scope: "REAL_LAUNCHER_UI", remote_prompt_limit: 1, started_at: new Date().toISOString() };
  const record = (change) => {
    receipt = { ...receipt, ...change, updated_at: new Date().toISOString() };
    writeFileSync(receiptPath, JSON.stringify(receipt, null, 2));
  };
  try {
    await page.emulateMedia({ reducedMotion: "reduce" });
    if (!receipt.task_path) {
      if (receipt.phase) throw new Error("REGISTRATION_OUTCOME_REQUIRES_INSPECTION");
      await page.getByRole("button", { name: "检查 WMA 发布连接", exact: true }).click();
      await expect(page.getByTestId("dispatch-readiness")).toHaveText("已就绪：可以在调查任务上发起调查。", { timeout: 90000 });
      await page.getByLabel("已批准来源").selectOption("01a08f03-991f-7368-8d87-ca813a1b267b/01a08f03-991f-7368-8d87-ca82caf08586");
      await page.getByLabel("执行时间上限（秒）").fill("1800");
      record({ phase: "REGISTERING" });
      await page.getByRole("button", { name: "登记调查任务", exact: true }).click();
      const registered = page.getByRole("link", { name: "查看已登记任务", exact: true });
      await expect(registered).toBeVisible({ timeout: 30000 });
      const taskPath = await registered.getAttribute("href");
      if (!/^\/review\/investigations\/[0-9a-f-]{36}$/.test(taskPath ?? "")) throw new Error("TASK_RECEIPT_INVALID");
      record({ phase: "REGISTERED", task_path: taskPath });
    }
    if (!/^\/review\/investigations\/[0-9a-f-]{36}$/.test(receipt.task_path)) throw new Error("TASK_RECEIPT_INVALID");
    await page.goto(`${origin}${receipt.task_path}`, { timeout: 30000 });
    if (receipt.phase === "REGISTERED") {
      record({ phase: "DISPATCHING" });
      await page.getByRole("button", { name: "发起调查", exact: true }).click();
      await expect(page.getByRole("status").filter({ hasText: "已发起调查" })).toBeVisible({ timeout: 30000 });
      record({ phase: "DISPATCHED" });
    }
    const deadline = Date.now() + 35 * 60 * 1000;
    while (Date.now() < deadline) {
      await page.reload({ timeout: 30000 });
      const status = await page.locator("main[data-investigation-status]").getAttribute("data-investigation-status");
      if (status !== receipt.task_status) record({ task_status: status });
      if (["PENDING_REVIEW", "APPROVED"].includes(status)) {
        record({ verification_step: "DOCUMENT_ENTRY" });
        await expect(page.getByRole("heading", { name: "文档证据准备", exact: true })).toBeVisible();
        record({ verification_step: "DELIVERY_SCREENSHOT" });
        await page.bringToFront();
        await page.getByRole("heading", { name: "文档证据准备", exact: true }).scrollIntoViewIfNeeded();
        await page.screenshot({ path: join(directory, "real-investigation-delivered.png") });
        record({ verification_step: "DOCUMENT_PREPARATION" });
        await page.getByRole("button", { name: "准备文档证据", exact: true }).click();
        const documents = page.getByRole("region", { name: "文档证据准备", exact: true });
        await expect(documents.getByText(/份材料已完成文档证据准备|已准备 \d+\/\d+ 份/)).toBeVisible({ timeout: 90000 });
        const needsAttention = await documents.getByText("仍有未准备、需复核或不支持的材料，请逐项处理。", { exact: true }).isVisible();
        await documents.getByRole("heading", { name: "文档证据准备", exact: true }).scrollIntoViewIfNeeded();
        await page.screenshot({ path: join(directory, "real-investigation-documents.png") });
        record({ document_preparation: needsAttention ? "NEEDS_ATTENTION" : "PREPARED", verification_step: "INTERNAL_REVIEW_BOUNDARY" });
        record({ phase: "DELIVERED", independent_review: "NOT_PERFORMED_BY_VERIFIER" });
        return;
      }
      if (["FAILED_PREPARATION", "FAILED_VALIDATION", "EXECUTION_UNCERTAIN", "COLLECTION_RETRYABLE", "EXPIRED", "REJECTED"].includes(status)) {
        await page.screenshot({ path: join(directory, "real-investigation-needs-attention.png") });
        record({ phase: "NEEDS_ATTENTION" });
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 15000));
    }
    record({ phase: "WAIT_EXPIRED" });
  } catch (error) {
    record({ phase: "UI_ACCEPTANCE_FAILED", failed_at_phase: receipt.phase ?? "READINESS", error_name: error?.name ?? "Error" });
    // Leave the actual browser available to inspect the existing task, never retry.
  }
}
