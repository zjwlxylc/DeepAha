// Explicit local acceptance only: uses the launcher-owned browser and real API.
// Does not submit configuration, tasks, reviews or remote calls.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect } from "@playwright/test";

export async function verifyEntry(page, readyPath) {
  const root = fileURLToPath(new URL("../../", import.meta.url));
  const registry = JSON.parse(readFileSync(join(root, "config/sources/direct-wma-local.json"), "utf8"));
  const samples = JSON.parse(readFileSync(join(root, "config/sources/direct-wma-samples.json"), "utf8"));
  const checked = [];
  for (const source of registry.sources) for (const endpoint of source.endpoints) {
    const sample = samples.find((item) => item.endpoint_id === endpoint.endpoint_id);
    await page.getByLabel("已批准来源").selectOption(`${source.source.source_id}/${endpoint.endpoint_id}`, { timeout: 15000 });
    await expect(page.getByLabel("明确公告地址")).toHaveValue(endpoint.url);
    await expect(page.getByLabel("调查说明")).toHaveValue(sample.brief);
    checked.push({ title: sample.title, notice_url: endpoint.url });
    console.log(`INVESTIGATION_SAMPLE_VERIFIED ${checked.length}`);
  }
  const directory = dirname(readyPath);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: join(directory, "investigation-entry-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: join(directory, "investigation-entry-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  writeFileSync(join(directory, "investigation-entry-verification.json"), JSON.stringify({ verified_at: new Date().toISOString(), entry: page.url(), samples: checked, database_and_worker_visible: true, remote_calls: 0, scope: "LAUNCHER_ENTRY_ONLY" }, null, 2));
}
