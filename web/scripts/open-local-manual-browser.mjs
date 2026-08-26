import { existsSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";

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
const profilePath = option("--profile");
const identityPath = option("--identity");
const readyPath = option("--ready");
const identity = existsSync(identityPath)
  ? JSON.parse(readFileSync(identityPath, "utf8"))
  : null;

const browser = await chromium.launchPersistentContext(profilePath, { headless: false });

try {
  if (identity) {
    await browser.addCookies([
      {
        name: "deepaha_phase7_reviewer_session",
        value: identity.reviewer_session,
        url: origin,
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);
    unlinkSync(identityPath);
  }

  const pages = browser.pages();
  const consolePage = pages[0] ?? (await browser.newPage());
  await openReadyPage(consolePage, `${origin}/review/human-test`);
  writeFileSync(readyPath, '{"status":"ready"}\n', { encoding: "utf8", flag: "wx" });

  await new Promise((resolve) => browser.once("close", resolve));
} catch (error) {
  await browser.close();
  throw error;
}
