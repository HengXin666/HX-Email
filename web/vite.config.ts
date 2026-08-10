import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

import { brandRedirectPlugin } from "./brand_redirect_plugin";

const apiTarget = process.env.HX_EMAIL_API_TARGET ?? "http://127.0.0.1:8000";
const apiProxy = {
  "/api/v1": apiTarget,
  "/google": apiTarget,
};

export default defineConfig({
  plugins: [react(), brandRedirectPlugin()],
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
