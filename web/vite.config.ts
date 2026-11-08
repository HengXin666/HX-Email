import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

const apiTarget = process.env.HX_EMAIL_API_TARGET ?? "http://127.0.0.1:8000";
const apiProxy = {
  // ws: true 让订阅页的 WebSocket (/api/v1/router/subscriptions/{id}/ws) 也走代理
  "/api/v1": { target: apiTarget, ws: true },
  "/api/external": apiTarget,
  "/google": apiTarget,
};

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: apiProxy,
  },
  preview: {
    proxy: apiProxy,
  },
  test: {
    environment: "jsdom",
    exclude: [...configDefaults.exclude, "e2e/**"],
    setupFiles: "./src/test/setup.ts",
  },
});
