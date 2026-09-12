import { existsSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";

import { dirname, join } from "node:path";

import { chromium } from "@playwright/test";

function option(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || index + 1 >= process.argv.length) {
    throw new Error(`missing ${name}`);
  }
  return process.argv[index + 1];
}

async function openReadyPage(page, url) {
  const response = await page.goto(url, { timeout: 30000 });
  if (!response?.ok()) {
    throw new Error(`page did not open successfully: ${url}`);
  }
  await page.locator("h1").first().waitFor({ state: "visible", timeout: 30000 });
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
  await openReadyPage(consolePage, `${origin}/review/investigations`);
  console.log("INVESTIGATION_ENTRY_NAVIGATED");
  await consolePage.getByTestId("investigation-runtime").waitFor({ state: "visible", timeout: 30000 });
  await consolePage.getByText("调查处理进程运行中", { exact: true }).waitFor({ state: "visible", timeout: 30000 });
  console.log("INVESTIGATION_RUNTIME_VISIBLE");
  if (process.argv.includes("--verify-entry")) {
    const { verifyEntry } = await import("./verify-local-investigation-entry.mjs");
    await verifyEntry(consolePage, readyPath);
  }
  writeFileSync(readyPath, '{"status":"ready"}\n', { encoding: "utf8", flag: "wx" });

  if (process.argv.includes("--verify-investigation")) {
    const { verifyRealInvestigation } = await import("./verify-real-investigation.mjs");
    await verifyRealInvestigation(consolePage, readyPath);
  }

  await new Promise((resolve) => browser.once("close", resolve));
} catch (error) {
  console.error(error);
  const page = browser.pages()[0];
  if (page) await page.screenshot({ path: join(dirname(readyPath), "investigation-entry-failure.png") }).catch(() => {});
  await browser.close();
  throw error;
}
