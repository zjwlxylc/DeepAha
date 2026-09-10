import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: ["investigations.spec.ts", "announcement-snapshots.spec.ts", "group-sources.spec.ts", "group-facts.spec.ts", "group-rules.spec.ts", "group-rule-review.spec.ts", "group-applicability.spec.ts"],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "line",
  outputDir: "./output/playwright/investigations",
  use: { baseURL: "http://127.0.0.1:3096", browserName: "chromium" },
  projects: [
    { name: "desktop", use: { viewport: { width: 1280, height: 900 } } },
    { name: "mobile", use: { viewport: { width: 390, height: 844 } } },
  ],
  webServer: [
    { command: "node e2e/investigation-api.mjs", url: "http://127.0.0.1:3097/reset", reuseExistingServer: false },
    { command: "node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3096", url: "http://127.0.0.1:3096", env: { DEEPAHA_API_BASE_URL: "http://127.0.0.1:3097" }, reuseExistingServer: false },
  ],
});
