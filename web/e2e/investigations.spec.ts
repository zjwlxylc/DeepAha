import { expect, test } from "@playwright/test";
import { source, taskId, bindingTarget } from "../tests/investigations-fixture";

test.beforeEach(async ({ context, request }) => {
  await request.get("http://127.0.0.1:3097/reset");
  await context.addCookies([{ name: "deepaha_phase7_reviewer_session", value: "synthetic-browser-reviewer", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" }]);
});

for (const operation of ["registration", "review"] as const) {
  test(`retries ${operation} after a lost receipt without changing the form or duplicating a write`, async ({ page, request }) => {
    await page.goto(operation === "registration" ? "/review/investigations" : `/review/investigations/${taskId}`);
    const input = page.getByLabel(operation === "registration" ? "调查说明" : "核对理由");
    const button = page.getByRole("button", { name: operation === "registration" ? "登记调查任务" : "记录内部材料审核" });
    const form = page.locator("form").filter({ has: button });
    const requestKey = await form.locator('input[name="request_key"]').inputValue();
    if (operation === "registration") {
      await page.getByLabel("已批准来源").selectOption(`${source.source_id}/${source.endpoint_id}`);
      await page.getByLabel("明确公告地址").fill(`${source.url}/1`);
      await page.getByLabel("执行时间上限（秒）").fill("1200");
      await page.getByRole("checkbox").uncheck();
    } else {
      await page.getByRole("combobox", { name: "审核决定" }).selectOption("APPROVE");
    }
    await input.fill("合成浏览器测试：模拟后端提交成功但回执丢失。");
    await request.get("http://127.0.0.1:3097/drop-next-receipt");
    await button.click();
    await expect(page.locator("form").getByRole("alert")).toBeVisible();
    await expect(input).toHaveValue("合成浏览器测试：模拟后端提交成功但回执丢失。");
    await expect(form.locator('input[name="request_key"]')).toHaveValue(requestKey);
    if (operation === "registration") {
      await expect(page.getByLabel("执行时间上限（秒）")).toHaveValue("1200");
      await expect(page.getByRole("checkbox")).not.toBeChecked();
    } else await expect(page.getByRole("combobox", { name: "审核决定" })).toHaveValue("APPROVE");
    expect(await (await request.get("http://127.0.0.1:3097/receipts")).json()).toEqual({ mutations: 1, posts: 1 });
    await button.click();
    if (operation === "registration") await expect(page.getByRole("status")).toContainText("调查任务已登记");
    else await expect(page.getByText("批准内部材料", { exact: true })).toBeVisible();
    expect(await (await request.get("http://127.0.0.1:3097/receipts")).json()).toEqual({ mutations: 1, posts: 2 });
  });
}

test("retries document preparation after the receipt is lost", async ({ page, request }) => {
  await page.goto(`/review/investigations/${taskId}`);
  const button = page.getByRole("button", { name: "准备文档证据" });
  const form = page.locator("form").filter({ has: button });
  const requestKey = await form.locator('input[name="request_key"]').inputValue();
  await request.get("http://127.0.0.1:3097/drop-next-receipt");
  await button.click();
  await expect(form.getByRole("alert")).toBeVisible();
  await expect(form.locator('input[name="request_key"]')).toHaveValue(requestKey);
  await button.click();
  await expect(page.getByText("1 / 1 份材料已完成文档证据准备。")).toBeVisible();
  expect(await (await request.get("http://127.0.0.1:3097/receipts")).json()).toEqual({ mutations: 1, posts: 2 });
});

test("retries a binding with the same opportunity, positions and reason after a lost receipt", async ({ page, request }) => {
  await page.goto(`/review/investigations/${taskId}`);
  await page.getByRole("button", { name: "准备文档证据" }).click();
  await expect(page.getByText("1 / 1 份材料已完成文档证据准备。")).toBeVisible();
  await page.getByRole("combobox", { name: "审核决定" }).selectOption("APPROVE");
  await page.getByLabel("核对理由").fill("合成测试的材料准备");
  await page.getByRole("button", { name: "记录内部材料审核" }).click();
  const button = page.getByRole("button", { name: "确认归属并冻结来源" });
  const form = page.locator("form").filter({ has: button });
  const requestKey = await form.locator('input[name="request_key"]').inputValue();
  const target = page.getByRole("combobox", { name: "关联到已有机会" });
  const position = page.getByRole("combobox", { name: "教学岗位（P001）" });
  const reason = page.getByLabel("归属核对依据");
  const unit = bindingTarget.positions[0];
  await target.selectOption(`${bindingTarget.opportunity_id}/1`);
  await position.selectOption(`${unit.unit_id}/${unit.version_id}`);
  await reason.fill("合成测试：保留岗位版本和归属核对依据");
  await request.get("http://127.0.0.1:3097/drop-next-receipt");
  await button.click();
  await expect(form.getByRole("alert")).toBeVisible();
  await expect(form.locator('input[name="request_key"]')).toHaveValue(requestKey);
  await expect(target).toHaveValue(`${bindingTarget.opportunity_id}/1`);
  await expect(position).toHaveValue(`${unit.unit_id}/${unit.version_id}`);
  await expect(reason).toHaveValue("合成测试：保留岗位版本和归属核对依据");
  await button.click();
  await expect(page.getByText("已关联 1 个岗位，仍有 0 个岗位待关联。")).toBeVisible();
  expect(await (await request.get("http://127.0.0.1:3097/receipts")).json()).toEqual({ mutations: 3, posts: 4 });
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
  const prepare = page.getByRole("button", { name: "准备文档证据" });
  await prepare.focus();
  await prepare.press("Enter");
  await expect(page.getByText("1 / 1 份材料已完成文档证据准备。")).toBeVisible();
  await expect(page.getByText("文档证据已准备，语义待核对")).toBeVisible();
  await expect(page.getByText("内容：找到原文 · 定位：声明定位成立")).toBeVisible();
  await expect(page.getByText("持久证据：已关联 EvidenceRef · 通过")).toBeVisible();
  await page.getByText("核验依据与候选位置").click();
  await expect(page.getByText(/Reader：xlsx_literal/)).toBeVisible();
  await page.reload();
  await expect(page.getByText("1 / 1 份材料已完成文档证据准备。")).toBeVisible();
  await page.getByText("核验依据与候选位置").click();
  await page.getByText("核验版本与历史").click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("documents.png"), fullPage: true });
  await page.getByRole("combobox", { name: "审核决定" }).selectOption("APPROVE");
  await page.getByLabel("核对理由").fill("合成浏览器测试：核对界面流程，不构成真实人工审核证据。");
  await page.getByRole("button", { name: "记录内部材料审核" }).click();
  await expect(page.getByText("批准内部材料", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "记录内部材料审核" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "确认归属并冻结来源" })).toBeDisabled();
  await page.getByRole("combobox", { name: "关联到已有机会" }).selectOption(`${bindingTarget.opportunity_id}/1`);
  const unit = bindingTarget.positions[0];
  await page.getByRole("combobox", { name: "教学岗位（P001）" }).selectOption(`${unit.unit_id}/${unit.version_id}`);
  await page.getByLabel("归属核对依据").fill("合成浏览器测试：岗位编号一致，只验证操作流程。");
  const confirm = page.getByRole("button", { name: "确认归属并冻结来源" });
  await confirm.focus(); await confirm.press("Enter");
  await expect(page.getByText("已关联 1 个岗位，仍有 0 个岗位待关联。")).toBeVisible();
  await page.reload();
  await expect(page.getByText(/机会版本 1 · 归属修订 1/)).toBeVisible();
  await page.getByText("查看来源与归属记录").click();
  await expect(page.getByText(/Direct WMA；网址由调查服务声明/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("binding.png"), fullPage: true });
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

for (const withInitialPost of [true, false]) {
  test(`registers internal identity and retries ${withInitialPost ? "identity" : "additional positions"} without duplicate creation`, async ({ page, request }, testInfo) => {
    await page.goto(`/review/investigations/${taskId}`);
    await page.getByRole("button", { name: "准备文档证据" }).click();
    await expect(page.getByText("1 / 1 份材料已完成文档证据准备。")).toBeVisible();
    await page.getByRole("combobox", { name: "审核决定" }).selectOption("APPROVE");
    await page.getByLabel("核对理由").fill("合成测试，不是真人验收证据");
    await page.getByRole("button", { name: "记录内部材料审核" }).click();
    await page.getByText("首次登记新机会", { exact: true }).click();
    await page.getByLabel("机会名称", { exact: true }).fill("合成内部机会");
    await expect(page.getByLabel("机会类别")).toHaveValue("");
    await page.getByLabel("机会类别").selectOption("PUBLIC_INSTITUTION_JOB");
    await page.getByLabel("官方发布单位").fill("合成发布单位");
    await page.getByLabel("登记核对依据").fill("核对合成身份，仅用于工程测试");
    if (!withInitialPost) {
      await page.getByRole("button", { name: "登记内部机会并关联材料" }).click();
      await expect(page.getByText("已关联 0 个岗位，仍有 1 个岗位待关联。")).toBeVisible();
      await page.getByText("登记尚无身份的岗位", { exact: true }).click();
      await expect(page.getByLabel("机会名称", { exact: true })).toHaveCount(0);
      await page.getByLabel("登记核对依据").fill("补充合成岗位，不重新建立机会");
    }
    await page.getByRole("checkbox", { name: "教学岗位", exact: true }).check();
    await page.getByLabel("岗位名称", { exact: true }).fill("合成岗位一");
    await page.getByLabel("内部识别键（有官方编号时用编号）").fill("P-RETRY");
    const button = page.getByRole("button", { name: withInitialPost ? "登记内部机会并关联材料" : "登记岗位并保留已有归属" });
    const form = page.locator("form").filter({ has: button });
    const key = await form.locator('input[name="request_key"]').inputValue();
    await request.get("http://127.0.0.1:3097/drop-next-receipt");
    await button.click();
    await expect(form.getByRole("alert")).toBeVisible();
    await expect(form.locator('input[name="request_key"]')).toHaveValue(key);
    await expect(page.getByRole("checkbox", { name: "教学岗位", exact: true })).toBeChecked();
    await expect(page.getByLabel("岗位名称", { exact: true })).toHaveValue("合成岗位一");
    await expect(page.getByLabel("内部识别键（有官方编号时用编号）")).toHaveValue("P-RETRY");
    if (withInitialPost) {
      await expect(page.getByLabel("机会名称", { exact: true })).toHaveValue("合成内部机会");
      await expect(page.getByLabel("官方发布单位")).toHaveValue("合成发布单位");
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath("identity-retry.png"), fullPage: true });
    await button.click();
    await expect(page.getByText(/当前关联：合成内部机会/)).toBeVisible();
    await expect(page.getByText("已关联 1 个岗位，仍有 0 个岗位待关联。")).toBeVisible();
    const mutations = withInitialPost ? 3 : 4;
    expect(await (await request.get("http://127.0.0.1:3097/receipts")).json()).toEqual({ mutations, posts: mutations + 1 });
    await page.reload();
    await expect(page.getByText(`当前关联：合成内部机会 · 机会版本 1 · 归属修订 ${withInitialPost ? 1 : 2}`)).toBeVisible();
    await expect(page.getByText(/字段内容仍是候选/)).toBeVisible();
  });
}
