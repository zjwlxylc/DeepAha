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
  await expect(page.getByRole("combobox")).toHaveValue("");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  if (mode === "stale") await page.screenshot({ path: info.outputPath("context.png"), fullPage: true });
  await request.get(`${api}/group-context-mode?kind=${mode}`);
  await page.getByRole("button", { name: "重新读取当前上下文" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await expect(page.getByRole("heading", { name: "当前官方原文" })).toHaveCount(0);
  await request.get(`${api}/group-context-mode?kind=normal`);
  await page.getByRole("button", { name: "重新读取当前上下文" }).click();
  await expect(page.getByRole("heading", { name: "当前官方原文" })).toBeVisible();
  expect(await (await request.get(`${api}/group-context-receipts`)).json()).toEqual({ posts: 0, mutations: 0 });
});

for (const lost of [false, true]) test(`group applicability save reload and retry ${lost}`, async ({ page, request }, info) => {
  const c = await (await request.get(`${api}/seed-group-context`)).json();
  const path = `/review/investigations/${c.task_id}/unit-plans/${c.target_plan_id}/group-applicability/${c.source_rule_preparation_id}/${c.source_rule_candidate_id}`;
  await page.goto(path);
  await expect(page).toHaveURL(new RegExp(path + "$"));
  await page.getByRole("combobox").selectOption("APPLIES");
  await page.getByLabel("决定理由", { exact: true }).fill("Synthetic scope reviewed against the exact original");
  await page.getByRole("checkbox", { name: "引用原文 1", exact: true }).check();
  if (lost) await request.get(`${api}/group-context-mode?kind=lost-once`);
  await page.getByRole("button", { name: "保存适用性决定" }).click();
  if (lost) {
    await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
    await expect(page.getByRole("combobox")).toHaveCount(0);
    await page.getByRole("button", { name: "重试原请求" }).click();
  }
  await expect(page.getByText("第 1 次 · 适用于此岗位", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(path + "$"));
  await page.reload();
  await expect(page.getByText("第 1 次 · 适用于此岗位", { exact: true })).toBeVisible();
  await page.getByRole("combobox").selectOption("NEEDS_ADJUDICATION");
  await page.getByLabel("决定理由", { exact: true }).fill("Synthetic exception needs independent adjudication");
  await page.getByRole("button", { name: "保存适用性决定" }).click();
  await expect(page.getByText("第 2 次 · 待裁决", { exact: true })).toBeVisible();
  expect(await (await request.get(`${api}/group-context-receipts`)).json()).toEqual({ posts: lost ? 3 : 2, mutations: 2 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  if (!lost) await page.screenshot({ path: info.outputPath("group-decisions.png"), fullPage: true });
  await request.get(`${api}/group-context-mode?kind=stale`);
  await page.getByRole("button", { name: "重新读取当前上下文" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await expect(page.getByText("第 2 次 · 待裁决", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("combobox")).toHaveCount(0);
});
