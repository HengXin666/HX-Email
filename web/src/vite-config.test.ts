// @vitest-environment node

import type { AddressInfo } from "node:net";
import type { ViteDevServer } from "vite";
import { createServer } from "vite";
import { afterAll, beforeAll, describe, expect, test } from "vitest";
import { brandRedirectPlugin } from "../brand_redirect_plugin";
import config from "../vite.config";

describe("vite API proxy", () => {
  test("forwards backend routes from development and production preview", () => {
    const devProxy = config.server?.proxy;
    const previewProxy = config.preview?.proxy;

    expect(devProxy?.["/api/v1"]).toBe("http://127.0.0.1:8000");
    expect(previewProxy?.["/api/v1"]).toBe("http://127.0.0.1:8000");
  });
});

describe("brand pages redirects (dev server)", () => {
  let server: ViteDevServer;
  let baseUrl: string;

  beforeAll(async () => {
    // Boot a real dev server with only the brand plugin: reusing the full
    // exported config under vitest strips the plugin entries, so pass the
    // plugin explicitly instead (configFile: false keeps the loader out).
    server = await createServer({
      configFile: false,
      logLevel: "silent",
      plugins: [brandRedirectPlugin()],
      server: { port: 0, host: "127.0.0.1" },
    });
    await server.listen();
    const address = server.httpServer?.address() as AddressInfo;
    baseUrl = `http://127.0.0.1:${address.port}`;
  }, 30_000);

  afterAll(async () => {
    await server.close();
  });

  test("redirects clean brand paths to the static pages", async () => {
    const expected: Array<[string, string]> = [
      ["/", "/home.html"],
      ["/home", "/home.html"],
      ["/home/", "/home.html"],
      ["/privacy", "/privacy.html"],
      ["/privacy/", "/privacy.html"],
      ["/privacy-policy", "/privacy.html"],
    ];
    for (const [from, to] of expected) {
      const response = await fetch(`${baseUrl}${from}`, { redirect: "manual" });
      expect(response.status, from).toBe(302);
      expect(response.headers.get("location"), from).toBe(to);
    }
  });

  test("serves the static brand pages used by Google verification", async () => {
    const home = await fetch(`${baseUrl}/home.html`);
    expect(home.status).toBe(200);
    expect(await home.text()).toContain("多邮箱统一管理平台");

    const privacy = await fetch(`${baseUrl}/privacy.html`);
    expect(privacy.status).toBe(200);
    expect(await privacy.text()).toContain("隐私政策");
  });
});
