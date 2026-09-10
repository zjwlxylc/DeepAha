import { expect, test, type Page, type APIRequestContext } from "@playwright/test";
const api = "http://127.0.0.1:3097";
test.beforeEach(async ({ context, request }) => {
  await request.get(`${api}/reset`);
  await context.addCookies([{ name: "deepaha_phase7_reviewer_session", value: "synthetic-browser-reviewer", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" }]);
});
async function saved(page: Page, request: APIRequestContext) {
  const id = await (await request.get(`${api}/seed-group-rules`)).json();
  await page.goto(`/review/investigations/${id.task_id}/group-facts/${id.preparation_id}/rules`);
  await page.getByRole("link", { name: "进入独立规则审核", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/group-facts/${id.preparation_id}/rules/review$`));
  await page.getByRole("button", { name: "保存候选并进入审核", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/group-rules/[a-f0-9-]+$`));
  return page.url();
}
test("save address refresh, explicit approval and complete denominator", async ({ page, request }, info) => {
  const address = await saved(page, request); await page.reload(); await expect(page).toHaveURL(address);
  await expect(page.getByRole("article")).toHaveCount(3);
  await expect(page.getByRole("combobox", { name: "权威类别", exact: true })).toHaveValue("");
  await page.getByRole("combobox", { name: "审核决定", exact: true }).selectOption("APPROVE"); await page.getByLabel("审核说明", { exact: true }).fill("已核对合成原件");
  await expect(page.getByRole("button", { name: "提交独立审核" })).toBeDisabled();
  await page.getByRole("combobox", { name: "权威类别", exact: true }).selectOption("FORMAL_OFFICIAL_ATTACHMENT");
  await page.getByRole("combobox", { name: "与规则的关系", exact: true }).selectOption("SUPPORTS");
  await page.getByLabel("官方材料生效时间（本地时区）", { exact: true }).fill("2026-09-01T08:00");
  await page.getByRole("combobox", { name: "适用范围", exact: true }).selectOption("APPLIES_TO_EXACT_TARGET");
  await page.getByLabel("证据评估说明", { exact: true }).fill("适用于本合成单位组");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("review.png"), fullPage: true });
  await page.getByRole("button", { name: "提交独立审核" }).click();
  await expect(page.getByRole("heading", { name: "审核结果：已批准" })).toBeVisible();
  await page.reload(); await expect(page.getByRole("heading", { name: "审核结果：已批准" })).toBeVisible();
  await expect(page.getByRole("article")).toHaveCount(3); await expect(page.getByRole("button", { name: "提交独立审核" })).toHaveCount(0);
  expect(await (await request.get(`${api}/group-fact-receipts`)).json()).toEqual({ posts: 2, mutations: 2 });
});
for (const kind of ["stale", "forbidden", "unavailable"]) test(`saved review hides old evidence on ${kind}`, async ({ page, request }) => {
  const address = await saved(page, request); await request.get(`${api}/group-fact-mode?kind=${kind}`);
  await page.reload(); await expect(page).toHaveURL(address);
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible(); await expect(page.getByRole("article")).toHaveCount(0);
  await request.get(`${api}/group-fact-mode?kind=normal`); await page.getByRole("button", { name: "重新读取当前审核" }).click();
  await expect(page.getByRole("article")).toHaveCount(3);
  expect(await (await request.get(`${api}/group-fact-receipts`)).json()).toEqual({ posts: 1, mutations: 1 });
});
test("lost decision response retries one mutation", async ({ page, request }) => {
  await saved(page, request); await page.getByRole("combobox", { name: "审核决定", exact: true }).selectOption("REJECT"); await page.getByLabel("审核说明", { exact: true }).fill("合成拒绝测试");
  await request.get(`${api}/group-fact-mode?kind=drop`); await page.getByRole("button", { name: "提交独立审核" }).click();
  await expect(page.getByRole("button", { name: "重试原提交（相同请求）" })).toBeVisible(); await expect(page.getByRole("article")).toHaveCount(0);
  await page.getByRole("button", { name: "重试原提交（相同请求）" }).click(); await expect(page.getByRole("heading", { name: "审核结果：已拒绝" })).toBeVisible();
  expect(await (await request.get(`${api}/group-fact-receipts`)).json()).toEqual({ posts: 3, mutations: 2 });
});
test("saved route response cannot expose an editable old start page", async ({ page, request }) => {
  const id = await (await request.get(`${api}/seed-group-rules`)).json();
  await page.goto(`/review/investigations/${id.task_id}/group-facts/${id.preparation_id}/rules/review`);
  let release!: () => void, fetched!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const received = new Promise<void>(resolve => { fetched = resolve; });
  await page.route("**/group-rules/**", async route => {
    const response = await route.fetch(); fetched(); await gate; await route.fulfill({ response });
  });
  try {
    await page.getByRole("button", { name: "保存候选并进入审核" }).click(); await received;
    await expect(page.getByRole("article")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "正在核对…" })).toBeDisabled();
    expect(await (await request.get(`${api}/group-fact-receipts`)).json()).toEqual({ posts: 1, mutations: 1 });
  } finally { release(); }
  await expect(page).toHaveURL(new RegExp(`/group-rules/[a-f0-9-]+$`));
  await expect(page.getByRole("article")).toHaveCount(3);
  await expect(page.getByRole("combobox", { name: "审核决定", exact: true })).toHaveValue("");
});
