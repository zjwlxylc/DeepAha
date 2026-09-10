import { expect, test } from "@playwright/test";
const api = "http://127.0.0.1:3097";
test.beforeEach(async ({ context, request }) => {
  await request.get(`${api}/reset`);
  await context.addCookies([{ name: "deepaha_phase7_reviewer_session", value: "synthetic-browser-reviewer", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" }]);
});
for (const mode of ["stale", "forbidden", "unavailable"]) test(`read-only context refresh and ${mode} recovery`, async ({ page, request }, info) => {
  const c = await (await request.get(`${api}/seed-group-context`)).json();
  const path = `/review/investigations/${c.task_id}/unit-plans/${c.target_plan_id}/group-applicability/${c.source_rule_preparation_id}/${c.source_rule_candidate_id}`;
  await page.goto(path);
  await expect(page).toHaveURL(new RegExp(path + "$"));
  await page.reload();
  await expect(page.getByRole("heading", { name: "尚未处理条件" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "完整成员清单" })).toBeVisible();
  await expect(page.getByRole("combobox")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  if (mode === "stale") await page.screenshot({ path: info.outputPath("context.png"), fullPage: true });
  await request.get(`${api}/group-context-mode?kind=${mode}`);
  await page.getByRole("button", { name: "重新读取当前上下文" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await expect(page.getByRole("heading", { name: "当前官方原文" })).toHaveCount(0);
  await request.get(`${api}/group-context-mode?kind=normal`);
  await page.getByRole("button", { name: "重新读取当前上下文" }).click();
  await expect(page.getByRole("heading", { name: "当前官方原文" })).toBeVisible();
  expect(await (await request.get(`${api}/group-context-receipts`)).json()).toEqual({ posts: 0 });
});
