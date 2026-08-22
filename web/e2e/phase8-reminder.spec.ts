import { expect, test, type Page } from "@playwright/test";

const WEB_ORIGIN = "http://localhost:3088";
const SYNTHETIC_OWNER_TOKEN = "phase8-synthetic-reminder-owner-token";

async function focusByKeyboard(page: Page, selector: string): Promise<void> {
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  const target = page.locator(selector);
  for (let index = 0; index < 20; index += 1) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((element) => document.activeElement === element)) {
      return;
    }
  }
  throw new Error(`keyboard focus did not reach ${selector}`);
}

async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.innerWidth);
}

test("owner can inspect and control the exact synthetic reminder on desktop and mobile", async ({
  context,
  page,
}) => {
  const browserProblems: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      browserProblems.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => browserProblems.push(`pageerror: ${error.message}`));
  await context.addCookies([
    {
      name: "deepaha_phase6_session",
      value: SYNTHETIC_OWNER_TOKEN,
      url: WEB_ORIGIN,
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/me/reminders");
  await expect(
    page.getByRole("heading", { level: 1, name: "截止变化提醒测试收件箱" }),
  ).toBeVisible();
  await expect(page.getByText("1 条不可变投递记录")).toBeVisible();
  await expect(page.getByText("2026-09-20", { exact: true })).toBeVisible();
  await expect(page.getByText("2026-09-30", { exact: true })).toBeVisible();
  await expect(page.getByText(/版本 6 → 7/)).toBeVisible();
  await expect(page.getByText("延后", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "查看变更前官方证据" })).toHaveAttribute(
    "href",
    "https://example.gov/synthetic/cancellation",
  );
  await expect(page.getByRole("link", { name: "查看当前官方证据" })).toHaveAttribute(
    "href",
    "https://example.gov/synthetic/deadline_extension",
  );
  await expect(page.getByRole("link", { name: "回到个人行动" })).toHaveAttribute(
    "href",
    "/me/opportunities/opp_63be197cc6ef3632650c5f69b5938f0b",
  );
  await expectNoHorizontalOverflow(page);

  const checkbox = page.locator("#deadline-reminder-enabled");
  const submit = page.getByRole("button", { name: "保存提醒设置" });
  await focusByKeyboard(page, "#deadline-reminder-enabled");
  await expect(checkbox).toBeFocused();
  await expect(checkbox).toBeChecked();
  await page.keyboard.press("Space");
  await expect(checkbox).not.toBeChecked();
  await page.keyboard.press("Tab");
  await expect(submit).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText("当前状态：未开启。此开关不会自动随收藏变化。"))
    .toBeVisible();
  await expect(page.getByText("1 条不可变投递记录")).toBeVisible();

  await focusByKeyboard(page, "#deadline-reminder-enabled");
  await page.keyboard.press("Space");
  await page.keyboard.press("Tab");
  await expect(submit).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText("当前状态：已开启。此开关不会自动随收藏变化。"))
    .toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByText("1 条不可变投递记录")).toBeVisible();
  await expectNoHorizontalOverflow(page);
  expect(browserProblems).toEqual([]);
});
