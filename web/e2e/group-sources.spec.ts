import { expect, test, type APIRequestContext } from "@playwright/test";
const api = "http://127.0.0.1:3097";
async function seed(request: APIRequestContext) {
  const id = await (await request.get(`${api}/seed-group-source`)).json();
  return { taskPath: `/review/investigations/${id.task_id}`, previewPath: `/review/investigations/${id.task_id}/group-source?entity_id=${id.entity_id}` };
}
test.beforeEach(async ({ context, request }) => {
  await request.get(`${api}/reset`);
  await context.addCookies([{ name: "deepaha_phase7_reviewer_session", value: "synthetic-browser-reviewer", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" }]);
});
test("complete membership, lost receipt retry and saved URL refresh", async ({ page, request }, info) => {
  const { taskPath } = await seed(request); await page.goto(taskPath);
  await page.getByRole("link", { name: "查看组来源：示例学院（合成）", exact: true }).click();
  await expect(page.getByRole("heading", { name: "完整组成员 · 2", exact: true })).toBeVisible();
  await expect(page.getByText("未处理 · UNPROCESSED", { exact: true })).toBeVisible();
  await expect(page.getByText(/不代表事实、规则或资格已批准/)).toBeVisible();
  expect(await (await request.get(`${api}/group-receipts`)).json()).toEqual({ posts: 0, mutations: 0 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("group-preview.png"), fullPage: true });
  await request.get(`${api}/group-mode?kind=drop`);
  await page.getByRole("button", { name: "登记当前组来源", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await expect(page.getByRole("heading", { name: "完整组成员 · 2", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "重试登记原摘要", exact: true }).click();
  const link = page.getByRole("link", { name: "打开已登记来源", exact: true }); await expect(link).toBeVisible();
  const path = await link.getAttribute("href"); expect(path).toMatch(/\/group-bindings\/[0-9a-f-]+$/);
  await link.click(); await expect(page).toHaveURL(`http://127.0.0.1:3096${path}`); await page.reload();
  await expect(page.getByRole("heading", { name: "已登记的组来源", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "登记当前组来源", exact: true })).toHaveCount(0);
  expect(await (await request.get(`${api}/group-receipts`)).json()).toEqual({ posts: 2, mutations: 1 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("group-saved.png"), fullPage: true });
});
test("changed preview requires explicit refresh and preserves the group ID across versions", async ({ page, request }, info) => {
  const { previewPath } = await seed(request); await page.goto(previewPath);
  await page.getByRole("button", { name: "登记当前组来源", exact: true }).click();
  const link = page.getByRole("link", { name: "打开已登记来源", exact: true }); await expect(link).toBeVisible();
  const oldPath = await link.getAttribute("href");
  const stableId = await page.getByText(/^unit_[0-9a-f]{32}$/).textContent();
  await link.click(); await expect(page).toHaveURL(`http://127.0.0.1:3096${oldPath}`);
  await request.get(`${api}/group-mode?kind=changed`); await page.reload();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await expect(page.getByRole("heading", { name: "完整组成员 · 2", exact: true })).toHaveCount(0);
  await page.screenshot({ path: info.outputPath("group-stale.png"), fullPage: true });
  await page.goto(previewPath); await page.getByRole("button", { name: "登记当前组来源", exact: true }).click();
  await expect(link).toBeVisible(); expect(await link.getAttribute("href")).not.toBe(oldPath);
  await expect(page.getByText(stableId!, { exact: true })).toBeVisible();
  expect(await (await request.get(`${api}/group-receipts`)).json()).toEqual({ posts: 2, mutations: 2 });
});
test("stale unsaved source cannot be submitted without a fresh preview", async ({ page, request }) => {
  const { previewPath } = await seed(request); await page.goto(previewPath);
  await expect(page.getByRole("button", { name: "登记当前组来源", exact: true })).toBeVisible();
  await request.get(`${api}/group-mode?kind=changed`); await page.getByRole("button", { name: "登记当前组来源", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试登记原摘要", exact: true })).toHaveCount(0);
  expect(await (await request.get(`${api}/group-receipts`)).json()).toEqual({ posts: 1, mutations: 0 });
  await page.getByRole("button", { name: "重新获取当前输入", exact: true }).click();
  await page.getByRole("button", { name: "登记当前组来源", exact: true }).click();
  await expect(page.getByRole("link", { name: "打开已登记来源", exact: true })).toBeVisible();
});
for (const kind of ["forbidden", "stale", "unavailable"]) {
  test(`hides saved source after ${kind} without a new write`, async ({ page, request }) => {
    const { previewPath } = await seed(request); await page.goto(previewPath);
    await page.getByRole("button", { name: "登记当前组来源", exact: true }).click();
    await expect(page.getByRole("heading", { name: "已登记的组来源", exact: true })).toBeVisible();
    await request.get(`${api}/group-mode?kind=${kind}`);
    await page.getByRole("button", { name: "重新核对已登记来源", exact: true }).click();
    await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
    await expect(page.getByRole("heading", { name: "完整组成员 · 2", exact: true })).toHaveCount(0);
    await expect(page.getByText("synthetic private group failure", { exact: true })).toHaveCount(0);
    expect(await (await request.get(`${api}/group-receipts`)).json()).toEqual({ posts: 1, mutations: 1 });
  });
}
