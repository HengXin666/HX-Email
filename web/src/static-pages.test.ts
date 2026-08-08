// @vitest-environment node

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Google OAuth brand verification requires two publicly reachable static pages
// (application homepage + privacy policy). These live in web/public so Vite
// copies them verbatim into dist and nginx serves them without authentication.
const HOME_HTML = readFileSync(new URL("../public/home.html", import.meta.url), "utf8");
const PRIVACY_HTML = readFileSync(new URL("../public/privacy.html", import.meta.url), "utf8");

describe("public brand pages", () => {
  it("exposes a self-contained homepage for brand verification", () => {
    expect(HOME_HTML).toContain("<title>HX-Email");
    expect(HOME_HTML).toContain('lang="zh-CN"');
    expect(HOME_HTML).toContain('href="/home.html"');
    expect(HOME_HTML).toContain('href="/privacy.html"');
    // The page must link back into the real app so it is a genuine landing page.
    expect(HOME_HTML).toContain('href="/login"');
  });

  it("covers the privacy-policy sections Google reviewers look for", () => {
    expect(PRIVACY_HTML).toContain("<title>隐私政策");
    expect(PRIVACY_HTML).toContain("生效日期");
    for (const section of [
      "我们收集的信息",
      "数据的存储",
      "数据的共享与披露",
      "数据安全",
      "数据保留与删除",
      "Cookie",
      "您的权利",
      "联系我们",
    ]) {
      expect(PRIVACY_HTML).toContain(section);
    }
    expect(PRIVACY_HTML).toContain('href="/home.html"');
  });
});
