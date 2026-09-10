import { defineConfig } from "@playwright/test";
export default defineConfig({ testDir: "./e2e", testMatch: "relation-review.spec.ts", workers: 1, retries: 0, reporter: "line",
  outputDir: "./output/playwright/relations", use: { baseURL: "http://127.0.0.1:3098", viewport: { width: 1440, height: 1000 } },
  webServer: [
    { command: "node e2e/relation-api.mjs", url: "http://127.0.0.1:3099/reset", reuseExistingServer: false },
    { command: "node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3098", url: "http://127.0.0.1:3098", env: { DEEPAHA_API_BASE_URL: "http://127.0.0.1:3099" }, reuseExistingServer: false },
  ],
});
