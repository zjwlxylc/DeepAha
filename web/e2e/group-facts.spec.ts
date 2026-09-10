import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
const api = "http://127.0.0.1:3097";
async function start(page: Page, request: APIRequestContext, legacy = false) {
  const id = await (await request.get(`${api}/seed-group-facts${legacy ? "?legacy=1" : ""}`)).json();
  await page.goto(`/review/investigations/${id.task_id}/group-bindings/${id.group_id}`);
  await page.getByRole("link", { name: "进入组字段审核", exact: true }).click();
  await expect(page.getByRole("button", { name: "准备组字段候选", exact: true })).toBeVisible();
}
async function openSaved(page: Page) {
  const link = page.getByRole("link", { name: "打开已保存审核记录", exact: true }); await expect(link).toBeVisible();
  const path = await link.getAttribute("href"); expect(path).toMatch(/\/group-facts\/[0-9a-f-]+$/);
  await link.click(); await expect(page).toHaveURL(`http://127.0.0.1:3096${path}`); await page.reload();
  await expect(page.getByRole("article", { name: "组字段：学历要求", exact: true })).toBeVisible();
}
test.beforeEach(async ({ context, request }) => {
  await request.get(`${api}/reset`);
  await context.addCookies([{ name: "deepaha_phase7_reviewer_session", value: "synthetic-browser-reviewer", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" }]);
});
test("explicit prepare, lost receipts, independent review and saved address refresh", async ({ page, request }, info) => {
  await start(page, request); expect(await (await request.get(`${api}/group-fact-receipts`)).json()).toEqual({ posts: 0, mutations: 0 });
  await request.get(`${api}/group-fact-mode?kind=drop`); await page.getByRole("button", { name: "准备组字段候选", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible(); await page.getByRole("button", { name: "重试原审核请求", exact: true }).click();
  await openSaved(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("group-facts-review.png"), fullPage: true });
  for (const [field, decision] of [["学历要求", "APPROVE"], ["户籍条件", "UNKNOWN"]]) {
    const row = page.getByRole("article", { name: `组字段：${field}`, exact: true });
    await row.getByRole("combobox", { name: "字段决定", exact: true }).selectOption(decision);
    await row.getByRole("combobox", { name: "原文是否支持候选", exact: true }).selectOption("SUPPORTED");
    await row.getByRole("combobox", { name: "更正与条件优先级", exact: true }).selectOption("PASSED");
    await row.getByLabel("审核依据", { exact: true }).fill(`合成测试：${field}独立审核`);
    await row.getByRole("button", { name: "记录字段审核", exact: true }).click();
    await expect(row.getByRole("status")).toBeVisible();
  }
  await page.getByLabel("保存依据", { exact: true }).fill("合成测试：组事实集保存");
  await request.get(`${api}/group-fact-mode?kind=drop`); await page.getByRole("button", { name: "保存组事实集", exact: true }).click();
  await expect(page.getByRole("article")).toHaveCount(0); await page.getByRole("button", { name: "重试原审核请求", exact: true }).click();
  await expect(page.getByText(/已保存组事实集 · ACTIVE/)).toBeVisible(); await page.reload();
  await expect(page.getByText(/已保存组事实集 · ACTIVE/)).toBeVisible();
  await expect(page.getByRole("article", { name: "组字段：Word 补充条件", exact: true })).toBeVisible();
  expect(await (await request.get(`${api}/group-fact-receipts`)).json()).toEqual({ posts: 6, mutations: 4 });
  await page.screenshot({ path: info.outputPath("group-facts-saved.png"), fullPage: true });
});
test("unknown cannot be approved and unresolved fields cannot be submitted", async ({ page, request }) => {
  await start(page, request); await page.getByRole("button", { name: "准备组字段候选", exact: true }).click(); await openSaved(page);
  const unknown = page.getByRole("article", { name: "组字段：户籍条件", exact: true });
  await expect(unknown.getByRole("option", { name: "批准字段", exact: true })).toHaveCount(0);
  await expect(page.getByRole("article", { name: "组字段：Word 补充条件", exact: true }).getByRole("button")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "保存组事实集", exact: true })).toHaveCount(0);
});
test("legacy display notes do not invalidate a frozen record", async ({ page, request }) => {
  await start(page, request, true); await page.getByRole("button", { name: "准备组字段候选", exact: true }).click(); await openSaved(page);
  await expect(page.getByRole("article")).toHaveCount(3); await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
});
for (const mode of ["stale", "forbidden", "unavailable"]) test(`saved record hides after ${mode}`, async ({ page, request }, info) => {
  await start(page, request); await page.getByRole("button", { name: "准备组字段候选", exact: true }).click(); await openSaved(page);
  await request.get(`${api}/group-fact-mode?kind=${mode}`); await page.reload();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible(); await expect(page.getByRole("article")).toHaveCount(0);
  expect(await (await request.get(`${api}/group-fact-receipts`)).json()).toEqual({ posts: 1, mutations: 1 });
  if (mode === "stale") await page.screenshot({ path: info.outputPath("group-facts-stale.png"), fullPage: true });
});
