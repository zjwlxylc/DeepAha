import { expect, test } from "@playwright/test";
import { source, taskId } from "../tests/investigations-fixture";

test.beforeEach(async ({ context, request }) => {
  await request.get("http://127.0.0.1:3097/reset");
  await context.addCookies([{ name: "deepaha_phase7_reviewer_session", value: "synthetic-browser-reviewer", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" }]);
});

test("registers without execution, reads evidence, downloads privately and records internal review", async ({ page }, testInfo) => {
  await page.goto("/review/investigations");
  await expect(page.getByRole("button", { name: "登记调查任务" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("list.png"), fullPage: true });
  await page.goto(`/review/investigations/${taskId}`);
  await expect(page.getByText("学历要求：硕士及以上")).toBeVisible();
  await expect(page.getByText("调查备注（待人工核对）")).toBeVisible();
  await expect(page.getByText("示例疑点：应届毕业生的证书取得时间仍需核对。")).toBeVisible();
  await expect(page.getByText(/工作表：岗位表；行：5；列：D/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("detail.png"), fullPage: true });
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载原件 · attachment-1" }).first().click();
  expect((await downloadPromise).suggestedFilename()).toBe("original-cccccccccccccccc.xlsx");
  await page.getByRole("combobox", { name: "审核决定" }).selectOption("APPROVE");
  await page.getByLabel("核对理由").fill("合成浏览器测试：核对界面流程，不构成真实人工审核证据。");
  await page.getByRole("button", { name: "记录内部材料审核" }).click();
  await expect(page.getByText("批准内部材料", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "记录内部材料审核" })).toHaveCount(0);
  await page.goto("/review/investigations");
  await page.getByLabel("已批准来源").selectOption(`${source.source_id}/${source.endpoint_id}`);
  await page.getByLabel("明确公告地址").fill(`${source.url}/1`);
  await page.getByLabel("调查说明").fill("只登记合成测试任务");
  await page.getByRole("button", { name: "登记调查任务" }).click();
  await expect(page.getByRole("status")).toContainText("调查任务已登记");
  await page.getByRole("link", { name: "查看已登记任务" }).click();
  await expect(page.getByText("已登记，等待执行", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /执行|恢复|开始调查/ })).toHaveCount(0);
});
