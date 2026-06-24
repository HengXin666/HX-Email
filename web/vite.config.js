var _a;
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
var apiTarget = (_a = process.env.HX_EMAIL_API_TARGET) !== null && _a !== void 0 ? _a : "http://127.0.0.1:8000";
export default defineConfig({
    plugins: [react()],
    server: {
        proxy: {
            "/admin": apiTarget,
            "/auth": apiTarget,
            "/data": apiTarget,
            "/email-accounts": apiTarget,
            "/groups": apiTarget,
            "/health": apiTarget,
            "/mail-pool": apiTarget,
            "/platform-bindings": apiTarget,
            "/platform-candidates": apiTarget,
            "/platforms": apiTarget,
            "/tags": apiTarget,
            "/temp-mail": apiTarget,
            "/usable-emails": apiTarget,
            "/workbench": apiTarget,
        },
    },
    test: {
        environment: "jsdom",
        setupFiles: "./src/test/setup.ts",
    },
});
