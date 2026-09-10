import { expect, test } from "@playwright/test";
const api = "http://127.0.0.1:3097";
test.beforeEach(async ({ context, request }) => {
  await request.get(`${api}/reset`);
  await context.addCookies([{ name: "deepaha_phase7_reviewer_session", value: "synthetic-browser-reviewer", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" }]);
});
test("saved group preview navigation and reload do not write", async ({ page, request }, info) => {
  const id = await (await request.get(`${api}/seed-group-rules`)).json();
  await page.goto(`/review/investigations/${id.task_id}/group-facts/${id.preparation_id}`);
  const link = page.getByRole("link", { name: "查看组规则预览（只读）", exact: true });
  const path = await link.getAttribute("href"); await link.click();
  await expect(page).toHaveURL(`http://127.0.0.1:3096${path}`); await page.reload();
  await expect(page.getByRole("heading", { name: "单位组规则预览", exact: true })).toBeVisible();
  await expect(page.getByRole("article")).toHaveCount(3);
  await expect(page.getByText("事实未知，不能形成资格规则", { exact: true })).toBeVisible();
  await expect(page.getByText("待处理：字段或证据尚不能用于规则", { exact: true })).toBeVisible();
  await expect(page.getByRole("combobox")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("preview.png"), fullPage: true });
  expect(await (await request.get(`${api}/group-fact-receipts`)).json()).toEqual({ posts: 0, mutations: 0 });
});
for (const kind of ["stale", "forbidden", "unavailable"]) test(`hides stale preview for ${kind} and recovers`, async ({ page, request }) => {
  const id = await (await request.get(`${api}/seed-group-rules`)).json();
  await page.goto(`/review/investigations/${id.task_id}/group-facts/${id.preparation_id}/rules`);
  await expect(page.getByRole("article")).toHaveCount(3);
  await request.get(`${api}/group-fact-mode?kind=${kind}`);
  await page.getByRole("button", { name: "重新读取当前预览", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible(); await expect(page.getByRole("article")).toHaveCount(0);
  await request.get(`${api}/group-fact-mode?kind=normal`);
  await page.getByRole("button", { name: "重新读取当前预览", exact: true }).click();
  await expect(page.getByRole("article")).toHaveCount(3);
  expect(await (await request.get(`${api}/group-fact-receipts`)).json()).toEqual({ posts: 0, mutations: 0 });
});
