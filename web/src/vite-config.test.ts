// @vitest-environment node

import type { AddressInfo } from "node:net";
import type { ViteDevServer } from "vite";
import { createServer } from "vite";
import { afterAll, beforeAll, describe, expect, test } from "vitest";
import config from "../vite.config";

describe("vite API proxy", () => {
  test("forwards backend routes from development and production preview", () => {
    const devProxy = config.server?.proxy;
    const previewProxy = config.preview?.proxy;

    expect(devProxy?.["/api/v1"]).toBe("http://127.0.0.1:8000");
    expect(previewProxy?.["/api/v1"]).toBe("http://127.0.0.1:8000");
  });
});

describe("brand pages served by the SPA (dev server)", () => {
  let server: ViteDevServer;
  let baseUrl: string;

  beforeAll(async () => {
    // Boot a real dev server so react-router brand routes fall back to the
    // SPA shell exactly like production nginx does.
    server = await createServer({
      configFile: false,
      logLevel: "silent",
      root: ".",
      server: { port: 0, host: "127.0.0.1" },
    });
    await server.listen();
    const address = server.httpServer?.address() as AddressInfo;
    baseUrl = `http://127.0.0.1:${address.port}`;
  }, 30_000);

  afterAll(async () => {
    await server.close();
  });

  test("serves the SPA shell (no redirect) at every brand URL", async () => {
    const brandPaths = [
      "/",
      "/home",
      "/home/",
      "/home.html",
      "/privacy",
      "/privacy-policy",
      "/privacy.html",
      "/terms",
      "/terms-of-service",
      "/terms.html",
    ];
    for (const path of brandPaths) {
      const response = await fetch(`${baseUrl}${path}`);
      expect(response.status, path).toBe(200);
      expect(await response.text(), path).toContain('<div id="root"></div>');
    }
  });
});
