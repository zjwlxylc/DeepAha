import { expect, test } from "@playwright/test";
const api = "http://127.0.0.1:3097";
test.beforeEach(async ({ context, request }) => {
  await request.get(`${api}/reset`);
  await context.addCookies([{ name: "deepaha_phase7_reviewer_session", value: "synthetic-browser-reviewer", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" }]);
});
for (const mode of ["stale", "forbidden", "unavailable"]) test(`group inheritance exact address reload and ${mode}`, async ({ page, request }, info) => {
  const { task, plan } = await (await request.get(`${api}/seed-group-inheritance`)).json();
  const path = `/review/investigations/${task}/unit-plans/${plan}/group-inheritance`;
  await page.goto(path);
  await expect(page).toHaveURL(new RegExp(path + "$"));
  await page.reload();
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(page.getByText("字段尚未处理")).toBeVisible();
  await expect(page.getByText(/不是资格结论/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  if (mode === "stale") await page.screenshot({ path: info.outputPath("inheritance.png"), fullPage: true });
  await request.get(`${api}/group-inheritance-mode?kind=${mode}`);
  await page.getByRole("button", { name: "重新读取当前预览" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await expect(page.getByRole("article")).toHaveCount(0);
  await request.get(`${api}/group-inheritance-mode?kind=normal`);
  await page.getByRole("button", { name: "重新读取当前预览" }).click();
  await expect(page.getByRole("article")).toHaveCount(2);
});
