// Synthetic engineering relationships; these fixtures do not record real human approval.
import { expect, test, type APIRequestContext } from "@playwright/test";

const fixtureApi = "http://127.0.0.1:3097";
async function seed(request: APIRequestContext) {
  const identity = await (await request.get(`${fixtureApi}/seed-announcement-snapshot`)).json();
  const basePath = `/review/investigations/${identity.task_id}/unit-plans/${identity.base_plan_id}`;
  return { basePath, previewPath: `${basePath}/announcement-snapshot` };
}
test.beforeEach(async ({ context, request }) => {
  await request.get(`${fixtureApi}/reset`);
  await context.addCookies([{ name: "deepaha_phase7_reviewer_session", value: "synthetic-browser-reviewer", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" }]);
});

test("previews the full source denominator and retries a lost announcement snapshot receipt", async ({ page, request }, testInfo) => {
  const { basePath } = await seed(request);
  await page.goto(basePath);
  await page.getByRole("link", { name: "查看公告继承快照", exact: true }).click();
  await expect(page.getByRole("heading", { name: "当前输入预览", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "继承的公告条件 · 1", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "明确排除的公告条件 · 1", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "仍待处理的公告条件 · 1", exact: true })).toBeVisible();
  const inherited = page.getByRole("region", { name: "继承的公告条件 · 1", exact: true });
  await expect(inherited.getByRole("link", { name: "查看适用性官方原文", exact: true })).toHaveAttribute("href", "https://example.test/announcement/0");
  expect(await inherited.locator("blockquote").textContent()).toBe("  保留公告适用范围原文。\n");
  const base = page.getByRole("region", { name: "完整基础条件快照", exact: true });
  await expect(base.getByText(/全调查共 8 个源字段/)).toBeVisible();
  await expect(base.getByText(/Word 补充说明尚未核验/)).toBeVisible();
  await expect(page.getByRole("link", { name: "查看公告继承快照", exact: true })).toHaveCount(0);
  await expect(page.getByText(/尚不能用于个人资格判断/)).toBeVisible();
  expect(await (await request.get(`${fixtureApi}/receipts`)).json()).toEqual({ mutations: 0, posts: 0 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("announcement-snapshot-initial.png"), fullPage: true });
  await page.screenshot({ path: testInfo.outputPath("announcement-snapshot-initial-viewport.png") });

  await request.get(`${fixtureApi}/drop-next-receipt`);
  await page.getByRole("button", { name: "保存当前派生快照", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await expect(page.getByRole("heading", { name: "完整基础条件快照", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "重试保存原摘要", exact: true })).toBeVisible();
  expect(await (await request.get(`${fixtureApi}/receipts`)).json()).toEqual({ mutations: 1, posts: 1 });
  await page.screenshot({ path: testInfo.outputPath("announcement-snapshot-lost-receipt.png"), fullPage: true });
  await page.getByRole("button", { name: "重试保存原摘要", exact: true }).click();
  await expect(page.getByRole("heading", { name: "已保存的范围记录", exact: true })).toBeVisible();
  expect(await (await request.get(`${fixtureApi}/receipts`)).json()).toEqual({ mutations: 1, posts: 2 });
  const recordLink = page.getByRole("link", { name: "打开已保存快照", exact: true });
  const recordPath = await recordLink.getAttribute("href");
  await recordLink.click();
  await expect(page).toHaveURL(`http://127.0.0.1:3096${recordPath}`);
  await page.reload();
  await expect(page.getByRole("heading", { name: "继承的公告条件 · 1", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "保存当前派生快照", exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("announcement-snapshot-saved.png"), fullPage: true });
  await page.screenshot({ path: testInfo.outputPath("announcement-snapshot-saved-viewport.png") });
});

test("rejects a stale preview and only saves explicitly refreshed announcement input", async ({ page, request }, testInfo) => {
  const { previewPath } = await seed(request);
  await page.goto(previewPath);
  await expect(page.getByRole("button", { name: "保存当前派生快照", exact: true })).toBeVisible();
  await request.get(`${fixtureApi}/announcement-snapshot-mode?kind=changed`);
  await page.getByRole("button", { name: "保存当前派生快照", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await expect(page.getByRole("heading", { name: "完整基础条件快照", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "重试保存原摘要", exact: true })).toHaveCount(0);
  expect(await (await request.get(`${fixtureApi}/receipts`)).json()).toEqual({ mutations: 0, posts: 1 });
  await page.screenshot({ path: testInfo.outputPath("announcement-snapshot-stale-input.png"), fullPage: true });
  await page.getByRole("button", { name: "重新获取当前输入", exact: true }).click();
  await expect(page.getByRole("heading", { name: "继承的公告条件 · 0", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "明确排除的公告条件 · 2", exact: true })).toBeVisible();
  expect(await (await request.get(`${fixtureApi}/receipts`)).json()).toEqual({ mutations: 0, posts: 1 });
  await page.getByRole("button", { name: "保存当前派生快照", exact: true }).click();
  await expect(page.getByRole("heading", { name: "已保存的范围记录", exact: true })).toBeVisible();
  expect(await (await request.get(`${fixtureApi}/receipts`)).json()).toEqual({ mutations: 1, posts: 2 });
});

test("a corrected applicability decision invalidates the saved view and creates a distinct snapshot", async ({ page, request }, testInfo) => {
  const { previewPath } = await seed(request);
  await page.goto(previewPath);
  await page.getByRole("button", { name: "保存当前派生快照", exact: true }).click();
  const savedLink = page.getByRole("link", { name: "打开已保存快照", exact: true });
  await expect(savedLink).toBeVisible();
  const firstPath = await savedLink.getAttribute("href");
  await savedLink.click();
  await expect(page).toHaveURL(`http://127.0.0.1:3096${firstPath}`);
  await request.get(`${fixtureApi}/announcement-snapshot-mode?kind=changed`);
  await page.reload();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await expect(page.getByRole("heading", { name: "完整基础条件快照", exact: true })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("announcement-snapshot-stale-record.png"), fullPage: true });
  await page.goto(previewPath);
  await expect(page.getByRole("heading", { name: "明确排除的公告条件 · 2", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "保存当前派生快照", exact: true }).click();
  await expect(savedLink).toBeVisible();
  expect(await savedLink.getAttribute("href")).not.toBe(firstPath);
  expect(await (await request.get(`${fixtureApi}/receipts`)).json()).toEqual({ mutations: 2, posts: 2 });
});

for (const kind of ["stale", "forbidden", "unavailable"] as const) {
  test(`hides announcement source content after ${kind} and requires explicit reloading`, async ({ page, request }, testInfo) => {
    const { previewPath } = await seed(request);
    await page.goto(previewPath);
    await expect(page.getByRole("heading", { name: "继承的公告条件 · 1", exact: true })).toBeVisible();
    await request.get(`${fixtureApi}/announcement-snapshot-mode?kind=${kind}`);
    await page.getByRole("button", { name: "重新获取当前输入", exact: true }).click();
    await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
    await expect(page.getByRole("heading", { name: "完整基础条件快照", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "保存当前派生快照", exact: true })).toHaveCount(0);
    await expect(page.getByText("synthetic private failure must not leak", { exact: true })).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath(`announcement-snapshot-${kind}.png`), fullPage: true });
    await request.get(`${fixtureApi}/announcement-snapshot-mode?kind=normal`);
    await page.getByRole("button", { name: "重新获取当前输入", exact: true }).click();
    await expect(page.getByRole("heading", { name: "继承的公告条件 · 1", exact: true })).toBeVisible();
    expect(await (await request.get(`${fixtureApi}/receipts`)).json()).toEqual({ mutations: 0, posts: 0 });
  });
}
