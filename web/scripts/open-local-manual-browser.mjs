import { existsSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { chromium } from "@playwright/test";

function option(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || index + 1 >= process.argv.length) {
    throw new Error(`missing ${name}`);
  }
  return process.argv[index + 1];
}

async function openReadyPage(page, url) {
  const response = await page.goto(url);
  if (!response?.ok()) {
    throw new Error(`page did not open successfully: ${url}`);
  }
  await page.locator("h1").first().waitFor({ state: "visible" });
}

const origin = option("--origin");
const runtimeDirectory = option("--runtime");
const identityPath = option("--identity");
const readyPath = option("--ready");
const identity = existsSync(identityPath)
  ? JSON.parse(readFileSync(identityPath, "utf8"))
  : null;

const personal = await chromium.launchPersistentContext(
  join(runtimeDirectory, "personal-browser"),
  { headless: false },
);
const reminder = await chromium.launchPersistentContext(
  join(runtimeDirectory, "reminder-browser"),
  { headless: false },
);

try {
  if (identity) {
    await personal.addCookies([
      {
        name: "deepaha_phase6_session",
        value: identity.personal_session,
        url: origin,
        httpOnly: true,
        sameSite: "Lax",
      },
      {
        name: "deepaha_phase7_reviewer_session",
        value: identity.reviewer_session,
        url: origin,
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);
    await reminder.addCookies([
      {
        name: "deepaha_phase6_session",
        value: identity.reminder_session,
        url: origin,
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);
    unlinkSync(identityPath);
  }

  const personalPages = personal.pages();
  const publicPage = personalPages[0] ?? (await personal.newPage());
  await openReadyPage(publicPage, `${origin}/opportunities`);
  const personalPage = await personal.newPage();
  await openReadyPage(personalPage, `${origin}/me/opportunities`);
  const reviewPage = await personal.newPage();
  await openReadyPage(reviewPage, `${origin}/review/feedback`);

  const reminderPages = reminder.pages();
  const reminderPage = reminderPages[0] ?? (await reminder.newPage());
  await openReadyPage(reminderPage, `${origin}/me/reminders`);
  writeFileSync(readyPath, '{"status":"ready"}\n', { encoding: "utf8", flag: "wx" });

  await Promise.all([
    new Promise((resolve) => personal.once("close", resolve)),
    new Promise((resolve) => reminder.once("close", resolve)),
  ]);
} catch (error) {
  await Promise.allSettled([personal.close(), reminder.close()]);
  throw error;
}
