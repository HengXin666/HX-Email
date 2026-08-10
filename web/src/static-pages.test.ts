// @vitest-environment node

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Google OAuth brand verification requires two publicly reachable static pages
// (application homepage + privacy policy). These live in web/public so Vite
// copies them verbatim into dist and nginx serves them without authentication.
const HOME_HTML = readFileSync(new URL("../public/home.html", import.meta.url), "utf8");
const PRIVACY_HTML = readFileSync(new URL("../public/privacy.html", import.meta.url), "utf8");
const TERMS_HTML = readFileSync(new URL("../public/terms.html", import.meta.url), "utf8");

describe("public brand pages", () => {
  it("exposes a self-contained homepage for brand verification", () => {
    expect(HOME_HTML).toContain("<title>HX-Email");
    expect(HOME_HTML).toContain('lang="zh-CN"');
    expect(HOME_HTML).toContain('href="/home.html"');
    expect(HOME_HTML).toContain('href="/privacy.html"');
    expect(HOME_HTML).toContain('href="/terms.html"');
    // The page must link back into the real app so it is a genuine landing page.
    expect(HOME_HTML).toContain('href="/login"');
    // The homepage has to state what the application is for.
    expect(HOME_HTML).toContain("集中管理");
    expect(HOME_HTML).toContain("验证码");
    // The OAuth consent-screen app name must match the homepage brand name.
    expect(HOME_HTML).toContain("HX-Email");
    expect(HOME_HTML).not.toContain("HX-EMail");
  });

  it("shows the app name prominently and supports bilingual content", () => {
    // The app name must be the visible H1 heading, not just a side mention.
    const h1 = HOME_HTML.match(/<h1[^>]*>([\s\S]*?)<\/h1>/)?.[1] ?? "";
    expect(h1.replace(/<[^>]+>/g, "").trim()).toBe("HX-Email");
    // Bilingual switcher with zh-CN default and an English option.
    expect(HOME_HTML).toContain('data-lang="zh-CN"');
    expect(HOME_HTML).toContain('data-lang="en"');
    expect(HOME_HTML).toContain("hx-home-lang");
    expect(HOME_HTML).toContain('"nav.console": "Open Console"');
    // A section that transparently explains why the app requests user data.
    expect(HOME_HTML).toContain('id="data"');
    expect(HOME_HTML).toContain("为什么 HX-Email 需要您的数据");
    expect(HOME_HTML).toContain("Why HX-Email Needs Your Data");
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

  it("provides a public terms-of-service page linked from the homepage", () => {
    expect(TERMS_HTML).toContain("<title>服务条款");
    expect(TERMS_HTML).toContain("生效日期");
    for (const section of ["服务说明", "账户与使用", "用户责任", "免责声明", "联系我们"]) {
      expect(TERMS_HTML).toContain(section);
    }
    expect(TERMS_HTML).toContain('href="/home.html"');
    expect(TERMS_HTML).toContain('href="/privacy.html"');
  });
});
