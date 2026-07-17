import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const WEB_ROOT = dirname(fileURLToPath(import.meta.url));
const REPOSITORY_ROOT = resolve(WEB_ROOT, "..");
const SERVER_ROOT = resolve(REPOSITORY_ROOT, "server");
const TEST_DATA_DIR = resolve(WEB_ROOT, "test-results/server-data");
const BACKEND_URL = "http://127.0.0.1:18080";
const FRONTEND_URL = "http://127.0.0.1:14173";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI
    ? [["line"], ["html", { open: "never" }]]
    : [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: FRONTEND_URL,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      name: "backend",
      command: `rm -rf "${TEST_DATA_DIR}" && uv run uvicorn hx_email.app:app --host 127.0.0.1 --port 18080`,
      cwd: SERVER_ROOT,
      env: {
        HX_EMAIL_ADMIN_PASSWORD: "admin",
        HX_EMAIL_ADMIN_USERNAME: "admin",
        HX_EMAIL_DATA_DIR: TEST_DATA_DIR,
      },
      url: `${BACKEND_URL}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      name: "frontend",
      command: "npm run build && npm run preview -- --host 127.0.0.1 --port 14173",
      cwd: WEB_ROOT,
      env: {
        HX_EMAIL_API_TARGET: BACKEND_URL,
      },
      url: `${FRONTEND_URL}/login`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
