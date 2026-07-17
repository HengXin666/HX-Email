var __spreadArray = (this && this.__spreadArray) || function (to, from, pack) {
    if (pack || arguments.length === 2) for (var i = 0, l = from.length, ar; i < l; i++) {
        if (ar || !(i in from)) {
            if (!ar) ar = Array.prototype.slice.call(from, 0, i);
            ar[i] = from[i];
        }
    }
    return to.concat(ar || Array.prototype.slice.call(from));
};
var _a;
import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";
var apiTarget = (_a = process.env.HX_EMAIL_API_TARGET) !== null && _a !== void 0 ? _a : "http://127.0.0.1:8000";
var apiProxy = {
    "/api/v1": apiTarget,
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
        exclude: __spreadArray(__spreadArray([], configDefaults.exclude, true), ["e2e/**"], false),
        setupFiles: "./src/test/setup.ts",
    },
});
