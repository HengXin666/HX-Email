// @vitest-environment node

import { describe, expect, test } from "vitest";

import config from "../vite.config";

describe("vite dev server proxy", () => {
  test("forwards backend routes to the local FastAPI server", () => {
    const proxy = config.server?.proxy;

    expect(proxy).toBeDefined();
    expect(proxy?.["/auth"]).toBe("http://127.0.0.1:8000");
    expect(proxy?.["/groups"]).toBe("http://127.0.0.1:8000");
    expect(proxy?.["/platforms"]).toBe("http://127.0.0.1:8000");
    expect(proxy?.["/workbench"]).toBe("http://127.0.0.1:8000");
  });
});
