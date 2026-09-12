import { expect, test } from "@playwright/test";
import { source, taskId, bindingTarget } from "../tests/investigations-fixture";
import { applicabilityIds } from "../tests/rule-applicability-fixture";

async function seedApplicability(request: import("@playwright/test").APIRequestContext) {
  const identity = await (await request.get("http://127.0.0.1:3097/seed-rule-applicability")).json();
  return { snapshotPath: `/review/investigations/${identity.task_id}/unit-plans/${identity.target_plan_id}`,
    reviewPath: `/review/investigations/${identity.task_id}/unit-plans/${identity.target_plan_id}/applicability/${identity.source_rule_preparation_id}/${identity.source_rule_candidate_id}` };
}

test.beforeEach(async ({ context, request }) => {
  await request.get("http://127.0.0.1:3097/reset");
  await context.addCookies([{ name: "deepaha_phase7_reviewer_session", value: "synthetic-browser-reviewer", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" }]);
});

test("new entry explains missing browser session and shows actual readiness after login", async ({ page, context }) => {
  await context.clearCookies();
  await page.goto("/review/investigations");
  await expect(page.getByRole("heading", { name: "需要本地审核登录" })).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: "一键启动入口" })).toBeVisible();
  await expect(page.getByRole("button", { name: "登记调查任务" })).toHaveCount(0);
  await context.addCookies([{ name: "deepaha_phase7_reviewer_session", value: "synthetic-browser-reviewer", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" }]);
  await page.reload();
  await expect(page.getByTestId("investigation-runtime")).toBeVisible();
  await expect(page.getByText("调查处理进程运行中", { exact: true })).toBeVisible();
  await expect(page.getByText("未配置", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "检查 WMA 发布连接" })).toBeDisabled();
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

test("records announcement applicability independently, retries a lost receipt and appends corrections", async ({ page, request }, testInfo) => {
  const { snapshotPath } = await seedApplicability(request);
  await page.goto(snapshotPath);
  await page.getByRole("link", { name: "审阅公告规则适用性" }).click();
  await expect(page.getByRole("heading", { name: "来源公告" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "目标岗位" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "适用性决定", exact: true })).toHaveValue("");
  await expect(page.getByText(/不解除整体 UNCERTAIN/)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("announcement-applicability-initial.png"), fullPage: true });
  await page.getByRole("combobox", { name: "适用性决定", exact: true }).selectOption("NEEDS_ADJUDICATION");
  await page.getByLabel("决定理由").fill("合成工程测试：尚待核对公告适用范围，不是真人批准。");
  await page.getByRole("button", { name: "保存适用性决定" }).click();
  await expect(page.getByText("当前决定：待裁决（第 1 次）")).toBeVisible();
  await expect(page.getByRole("combobox", { name: "适用性决定", exact: true })).toHaveValue("");

  await page.getByRole("combobox", { name: "适用性决定", exact: true }).selectOption("APPLIES");
  await page.getByLabel("决定理由").fill("合成工程测试：原文明确覆盖全部岗位。");
  await page.getByLabel("引用原文 1", { exact: true }).check();
  const quote = await page.getByRole("textbox", { name: "引用文字 1", exact: true }).inputValue();
  await request.get("http://127.0.0.1:3097/drop-next-receipt");
  await page.getByRole("button", { name: "保存适用性决定" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("决定理由")).toBeDisabled();
  await expect(page.getByRole("textbox", { name: "引用文字 1", exact: true })).toHaveValue(quote);
  await page.screenshot({ path: testInfo.outputPath("announcement-applicability-retry.png"), fullPage: true });
  await page.getByRole("button", { name: "重试原请求" }).click();
  await expect(page.getByText("当前决定：适用于此岗位（第 2 次）")).toBeVisible();

  await page.getByRole("button", { name: "加载更多原文" }).click();
  await expect(page.getByText("已加载当前可引用的全部原文块，共 2 块。")).toBeVisible();
  await expect(page.getByRole("article", { name: "原文块 2", exact: true }).getByRole("link", { name: "查看官方原文" })).toHaveAttribute("href", "https://example.test/notices/copied-announcement.html");
  await page.getByLabel("引用原文 2", { exact: true }).check();
  await page.getByRole("combobox", { name: "适用性决定", exact: true }).selectOption("DOES_NOT_APPLY");
  await page.getByLabel("决定理由").fill("合成工程测试：追加更正，保留前两次记录。");
  await page.getByRole("button", { name: "保存适用性决定" }).click();
  await expect(page.getByText("当前决定：不适用于此岗位（第 3 次）")).toBeVisible();
  expect(await (await request.get("http://127.0.0.1:3097/receipts")).json()).toEqual({ mutations: 3, posts: 4 });
  const history = await (await request.get("http://127.0.0.1:3097/applicability-records")).json();
  expect(history.map((item: { request: { previous_decision_id: string | null } }) => item.request.previous_decision_id)).toEqual([null, history[0].decision_id, history[1].decision_id]);
  expect(history[1].request.evidence[0].quote).toBe(quote);
  expect(history[2].request.evidence[0]).toMatchObject({ member_id: applicabilityIds.secondBlock, block_id: applicabilityIds.block });
  await page.reload();
  await expect(page.getByText("当前决定：不适用于此岗位（第 3 次）")).toBeVisible();
  await expect(page.getByText(/不解除整体 UNCERTAIN/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("announcement-applicability.png"), fullPage: true });
});

for (const kind of ["stale", "forbidden", "unavailable"]) {
  test(`hides applicability evidence after ${kind} response`, async ({ page, request }, testInfo) => {
    const { reviewPath } = await seedApplicability(request);
    await page.goto(reviewPath);
    await expect(page.getByRole("combobox", { name: "适用性决定", exact: true })).toBeVisible();
    await request.get(`http://127.0.0.1:3097/rule-applicability-mode?kind=${kind}`);
    await page.getByRole("button", { name: "重新读取最新状态" }).click();
    await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
    await expect(page.getByRole("combobox", { name: "适用性决定", exact: true })).toHaveCount(0);
    await expect(page.getByText("示例招聘公告", { exact: true })).toHaveCount(0);
    await expect(page.getByText("synthetic private failure must not leak")).toHaveCount(0);
    await page.reload();
    await expect(page.getByRole("heading", { name: "适用性审阅暂不可用" })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "适用性决定", exact: true })).toHaveCount(0);
    if (kind === "stale") await page.screenshot({ path: testInfo.outputPath("announcement-applicability-stale.png"), fullPage: true });
  });
}

test("does not mix evidence pages across changed applicability context", async ({ page, request }) => {
  const { reviewPath } = await seedApplicability(request);
  await page.goto(reviewPath);
  await page.getByLabel("引用原文 1", { exact: true }).check();
  await request.get("http://127.0.0.1:3097/rule-applicability-mode?kind=changed");
  await page.getByRole("button", { name: "加载更多原文" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("已变化");
  await expect(page.getByLabel("引用原文 1", { exact: true })).toHaveCount(0);
  expect(await (await request.get("http://127.0.0.1:3097/receipts")).json()).toEqual({ mutations: 0, posts: 0 });
});

test("keeps empty applicability evidence unresolved and rejects a stale open form", async ({ page, request }) => {
  const { reviewPath } = await seedApplicability(request);
  await request.get("http://127.0.0.1:3097/rule-applicability-mode?kind=empty");
  await page.goto(reviewPath);
  await expect(page.getByText("当前没有可引用的原文块。可记录待裁决及理由。")).toBeVisible();
  await page.getByRole("combobox", { name: "适用性决定", exact: true }).selectOption("NEEDS_ADJUDICATION");
  await page.getByLabel("决定理由").fill("合成工程测试：无可读依据，保持待裁决。");
  await request.get("http://127.0.0.1:3097/rule-applicability-mode?kind=stale");
  await page.getByRole("button", { name: "保存适用性决定" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("已变化");
  await expect(page.getByRole("combobox", { name: "适用性决定", exact: true })).toHaveCount(0);
  expect(await (await request.get("http://127.0.0.1:3097/receipts")).json()).toEqual({ mutations: 0, posts: 1 });
});

test("creates and reads a current unit snapshot with retry and stale evidence feedback", async ({ page, request }, testInfo) => {
  await request.get("http://127.0.0.1:3097/seed-unit-snapshot");
  await page.goto(`/review/investigations/${taskId}`);
  const button = page.getByRole("button", { name: "整理条件快照" });
  const form = page.locator("form").filter({ has: button });
  const key = await form.locator('input[name="request_key"]').inputValue();
  await request.get("http://127.0.0.1:3097/drop-next-receipt");
  await button.click();
  await expect(form.getByRole("alert")).toHaveText(/可保留当前输入重试/);
  await expect(form.locator('input[name="request_key"]')).toHaveValue(key);
  await button.click();
  await page.getByRole("link", { name: "查看条件快照", exact: true }).click();
  await expect(page.getByRole("heading", { name: /教学岗位 · 条件快照/ })).toBeVisible();
  await expect(page.getByText(/通过 4 · 错误 0 · 未核验 1/)).toBeVisible();
  await expect(page.getByText(/调查后信息不足/)).toBeVisible();
  await expect(page.getByText(/证据尚不能定位核验/)).toBeVisible();
  await expect(page.getByText(/已拒绝，仍待处理/)).toBeVisible();
  await expect(page.getByText(/原始备注：示例疑点/)).toBeVisible();
  expect(await (await request.get("http://127.0.0.1:3097/receipts")).json()).toEqual({ mutations: 1, posts: 2 });
  await page.reload();
  await expect(page.getByText(/整体资格保持不确定/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("unit-snapshot.png"), fullPage: true });
  await request.get("http://127.0.0.1:3097/stale-unit-snapshot");
  await page.reload();
  await expect(page.getByRole("main").getByRole("alert")).toHaveText(/快照暂不可用/);
  await expect(page.getByRole("heading", { name: "逐项条件与依据" })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("unit-snapshot-stale.png") });
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

test("reviews rules independently and retries each lost response", async ({ page, request }, testInfo) => {
  await request.get("http://127.0.0.1:3097/seed-rule-review");
  await page.goto(`/review/investigations/${taskId}`);
  const panel = page.getByRole("region", { name: "规则候选与独立审核" });
  for (const kind of ["prepare", "pending", "approve"]) {
    if (kind !== "prepare") {
      for (const label of ["规则决定", "证据权威级别", "与拟规则的关系", "是否适用于此目标", "证据生效时间（含时区）"]) await expect(panel.getByLabel(label)).toHaveValue("");
      await panel.getByLabel("规则决定").selectOption(kind === "pending" ? "NEEDS_ADJUDICATION" : "APPROVE");
      await panel.getByLabel("是否适用于此目标").selectOption(kind === "pending" ? "UNRESOLVED" : "APPLIES_TO_EXACT_TARGET");
      if (kind === "approve") {
        await panel.getByLabel("证据权威级别").selectOption("FORMAL_OFFICIAL_ATTACHMENT");
        await panel.getByLabel("与拟规则的关系").selectOption("SUPPORTS");
        await panel.getByLabel("证据生效时间（含时区）").fill("2026-09-07T10:30:00+08:00");
      }
      await panel.getByLabel("证据判断依据").fill("合成证据判断，不代替真人审查");
      await panel.getByLabel("规则审核依据").fill("合成独立规则决定");
    }
    const name = kind === "prepare" ? "整理规则候选" : "记录规则审核";
    const button = panel.getByRole("button", { name });
    const form = panel.locator("form").filter({ has: page.getByRole("button", { name }) });
    const key = await form.locator('input[name="request_key"]').inputValue();
    await request.get("http://127.0.0.1:3097/drop-next-receipt");
    await button.click(); await expect(form.getByRole("alert")).toBeVisible();
    await expect(form.locator('input[name="request_key"]')).toHaveValue(key);
    if (kind !== "prepare") await expect(panel.getByLabel("证据判断依据")).toHaveValue("合成证据判断，不代替真人审查");
    if (kind === "approve") {
      await expect(panel.getByLabel("证据生效时间（含时区）")).toHaveValue("2026-09-07T10:30:00+08:00");
      await panel.screenshot({ path: testInfo.outputPath("rule-review-retry.png") });
    }
    await button.click();
    if (kind === "prepare") await expect(panel.getByLabel("规则决定")).toBeVisible();
    if (kind === "pending") await expect(panel.getByText(/规则审核：需要进一步裁决/)).toBeVisible();
    if (kind === "approve") await expect(panel.getByText(/规则审核：批准拟规则/)).toBeVisible();
  }
  expect(await (await request.get("http://127.0.0.1:3097/receipts")).json()).toEqual({ mutations: 3, posts: 6 });
  await page.reload();
  await expect(panel.getByRole("button", { name: "记录规则审核" })).toHaveCount(0);
  await panel.getByText("历次规则审核与证据判断", { exact: true }).click();
  await expect(panel.getByText(/NEEDS_ADJUDICATION/)).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await panel.screenshot({ path: testInfo.outputPath("rule-review.png") });
});

test("reviews field facts through the shared evidence receipt and retries each lost response", async ({ page, request }, testInfo) => {
  await page.goto(`/review/investigations/${taskId}`);
  await page.getByRole("button", { name: "准备文档证据" }).click();
  await expect(page.getByText("1 / 1 份材料已完成文档证据准备。")).toBeVisible();
  await page.getByRole("combobox", { name: "审核决定" }).selectOption("APPROVE");
  await page.getByLabel("核对理由").fill("合成字段流程测试，非真实人工审批");
  await page.getByRole("button", { name: "记录内部材料审核" }).click();
  await page.getByText("首次登记新机会", { exact: true }).click();
  await page.getByLabel("机会名称", { exact: true }).fill("合成字段审核机会");
  await page.getByLabel("机会类别").selectOption("PUBLIC_INSTITUTION_JOB");
  await page.getByLabel("官方发布单位").fill("合成发布单位");
  await page.getByRole("checkbox", { name: "教学岗位", exact: true }).check();
  await page.getByLabel("登记核对依据").fill("合成岗位，仅验证系统流程");
  await page.getByRole("button", { name: "登记内部机会并关联材料" }).click();
  const panel = page.getByRole("region", { name: "候选字段与独立审核" });
  for (const kind of ["prepare", "pending", "decision", "promote"]) {
    if (kind === "pending" || kind === "decision") {
      await expect(panel.getByLabel("字段决定")).toHaveValue("");
      await expect(panel.getByLabel("原文是否支持该规范值")).toHaveValue("");
      await expect(panel.getByRole("button", { name: "保存审核事实集" })).toHaveCount(0);
      await panel.getByLabel("字段决定").selectOption(kind === "pending" ? "NEEDS_ADJUDICATION" : "APPROVE");
      await panel.getByLabel("原文是否支持该规范值").selectOption(kind === "pending" ? "UNKNOWN" : "SUPPORTED");
      await panel.getByLabel("更正、适用范围与例外核查").selectOption(kind === "pending" ? "UNKNOWN" : "PASSED");
      await panel.getByLabel("本次审核依据").fill("合成独立审核说明，非真实事实确认");
    }
    if (kind === "decision") {
      await panel.getByText("查看准确位置和完整证据块").click();
      await panel.getByText("核验依据与候选位置").click();
      await expect(panel.getByText(/Reader：xlsx_literal/)).toBeVisible();
    }
    if (kind === "promote") await panel.getByLabel("本次审核依据").fill("保存合成已审核字段，不生成资格");
    const name = kind === "prepare" ? "整理字段候选与证据" : kind === "promote" ? "保存审核事实集" : "记录字段审核";
    const button = panel.getByRole("button", { name });
    const form = panel.locator("form").filter({ has: page.getByRole("button", { name }) });
    const key = await form.locator('input[name="request_key"]').inputValue();
    await request.get("http://127.0.0.1:3097/drop-next-receipt");
    await button.click();
    await expect(form.getByRole("alert")).toBeVisible();
    await expect(form.locator('input[name="request_key"]')).toHaveValue(key);
    if (kind === "decision") {
      await expect(panel.getByLabel("字段决定")).toHaveValue("APPROVE");
      await expect(panel.getByLabel("本次审核依据")).toHaveValue("合成独立审核说明，非真实事实确认");
      await panel.screenshot({ path: testInfo.outputPath("field-review-retry.png") });
    }
    if (kind === "promote") await expect(panel.getByLabel("本次审核依据")).toHaveValue("保存合成已审核字段，不生成资格");
    await button.click();
    if (kind === "prepare") await expect(panel.getByText(/共 1 个原始字段；1 个已接入审核/)).toBeVisible();
    if (kind === "pending") await expect(panel.getByText(/审核：需要进一步裁决/)).toBeVisible();
    if (kind === "decision") await expect(panel.getByText(/审核：批准字段/)).toBeVisible();
    if (kind === "promote") await expect(panel.getByText(/已保存审核事实集，状态：ACTIVE/)).toBeVisible();
  }
  expect(await (await request.get("http://127.0.0.1:3097/receipts")).json()).toEqual({ mutations: 7, posts: 11 });
  await page.reload();
  await expect(panel.getByText(/尚不代表完整资格判断/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await panel.screenshot({ path: testInfo.outputPath("field-review.png") });
});
