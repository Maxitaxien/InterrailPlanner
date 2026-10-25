import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/e2e", fullyParallel: false, workers: 1,
  use: { baseURL: "http://127.0.0.1:3000", headless: true, screenshot: "only-on-failure", trace: "retain-on-failure" },
  webServer: [
    { command: "node tests/start-backend.mjs", url: "http://127.0.0.1:8000/api/v1/health", reuseExistingServer: false, timeout: 30000 },
    { command: "node tests/start-frontend.mjs", url: "http://127.0.0.1:3000", reuseExistingServer: false, timeout: 30000 },
  ],
});
