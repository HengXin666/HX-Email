// @vitest-environment node

import { describe, expect, test } from "vitest";

import config from "../vite.config";

describe("vite API proxy", () => {
  test("forwards backend routes from development and production preview", () => {
    const devProxy = config.server?.proxy;
    const previewProxy = config.preview?.proxy;

    expect(devProxy?.["/api/v1"]).toBe("http://127.0.0.1:8000");
    expect(previewProxy?.["/api/v1"]).toBe("http://127.0.0.1:8000");
  });
});
