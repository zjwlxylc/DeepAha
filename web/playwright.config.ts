import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig } from "@playwright/test";

const apiBaseUrl = "http://127.0.0.1:8008";
const webBaseUrl = "http://localhost:3088";

process.env.DEEPAHA_API_BASE_URL = apiBaseUrl;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: "line",
  outputDir: join(tmpdir(), "deepaha-phase8-playwright"),
  preserveOutput: "never",
  use: {
    baseURL: webBaseUrl,
    browserName: "chromium",
    screenshot: "off",
    trace: "off",
    video: "off",
  },
  webServer: [
    {
      command:
        "uv run uvicorn --app-dir src deepaha.main:app --host 127.0.0.1 --port 8008",
      cwd: "../backend",
      url: `${apiBaseUrl}/api/v1/health/ready`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "pnpm start --hostname 127.0.0.1 --port 3088",
      cwd: ".",
      url: webBaseUrl,
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
