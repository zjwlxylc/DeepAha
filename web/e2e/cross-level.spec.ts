import { expect, test } from "@playwright/test";
const api = "http://127.0.0.1:3097";
test.beforeEach(async ({ context, request }) => {
  await request.get(`${api}/reset`);
  await context.addCookies([{ name: "deepaha_phase7_reviewer_session", value: "synthetic-browser-reviewer", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" }]);
});
for (const mode of ["stale", "forbidden", "unavailable"]) test(`cross-level complete scopes, exact address and ${mode}`, async ({ page, request }, info) => {
  const { task, plan } = await (await request.get(`${api}/seed-cross-level`)).json();
  const path = `/review/investigations/${task}/unit-plans/${plan}/cross-level`;
  await page.goto(path);
  await expect(page).toHaveURL(new RegExp(path + "$"));
  await page.reload();
  await expect(page.getByRole("article")).toHaveCount(4);
  await expect(page.getByText("全部条件 4 项 · 岗位层 1 · 继承范围 1 · 明确不适用 1 · 待处理 1")).toBeVisible();
  await expect(page.getByText(/不是资格结论/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const relation = page.getByRole("heading", { name: "同字段跨层级关系" }).locator("..");
  const anchor = relation.getByRole("link").last();
  const href = await anchor.getAttribute("href");
  await anchor.click();
  await expect(page).toHaveURL(new RegExp(path + href + "$"));
  await expect(page.locator(`[id="${decodeURIComponent(href!.slice(1))}"]`)).toBeInViewport();
  if (mode === "stale") {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: info.outputPath("cross-level.png"), fullPage: true });
  }
  await request.get(`${api}/cross-level-mode?kind=${mode}`);
  await page.getByRole("button", { name: "重新读取当前预览" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await expect(page.getByRole("article")).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await expect(page.getByRole("article")).toHaveCount(0);
  await request.get(`${api}/cross-level-mode?kind=normal`);
  await page.getByRole("button", { name: "重新读取当前预览" }).click();
  await expect(page.getByRole("article")).toHaveCount(4);
});
