// @vitest-environment node

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Google OAuth brand verification requires two publicly reachable static pages
// (application homepage + privacy policy). These live in web/public so Vite
// copies them verbatim into dist and nginx serves them without authentication.
const HOME_HTML = readFileSync(new URL("../public/home.html", import.meta.url), "utf8");
const PRIVACY_HTML = readFileSync(new URL("../public/privacy.html", import.meta.url), "utf8");
const TERMS_HTML = readFileSync(new URL("../public/terms.html", import.meta.url), "utf8");
const MANIFEST = JSON.parse(
  readFileSync(new URL("../public/manifest.webmanifest", import.meta.url), "utf8"),
) as {
  name: string;
  short_name: string;
  icons: Array<{ src: string; sizes: string; type: string }>;
};
const ROBOTS_TXT = readFileSync(new URL("../public/robots.txt", import.meta.url), "utf8");

describe("public brand pages", () => {
  it("exposes a self-contained homepage for brand verification", () => {
    expect(HOME_HTML).toContain("<title>HX-Email</title>");
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

  it("pins the app identity consistently across every extractable field", () => {
    // Google reviewers can pull the app name from several places; every one
    // must match the OAuth consent-screen name "HX-Email" exactly.
    for (const needle of [
      '<meta name="application-name" content="HX-Email" />',
      '<meta name="apple-mobile-web-app-title" content="HX-Email" />',
      '<meta property="og:title" content="HX-Email" />',
      '<meta property="og:site_name" content="HX-Email" />',
      '<link rel="manifest" href="/manifest.webmanifest" />',
    ]) {
      expect(HOME_HTML).toContain(needle);
    }
    const ldJson =
      HOME_HTML.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/)?.[1] ?? "";
    expect(JSON.parse(ldJson)).toMatchObject({
      "@type": "SoftwareApplication",
      name: "HX-Email",
    });
    expect(MANIFEST.name).toBe("HX-Email");
    expect(MANIFEST.short_name).toBe("HX-Email");
  });

  it("uses one consistent app icon across favicon, manifest and nav logo", () => {
    expect(HOME_HTML).toContain('<link rel="icon" type="image/svg+xml" href="/favicon.svg" />');
    expect(HOME_HTML).toContain('<link rel="apple-touch-icon" href="/icon-192.png" />');
    expect(HOME_HTML).toContain('src="/favicon.svg"');
    expect(MANIFEST.icons).toEqual([
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ]);
    // Favicon file itself exists next to the brand pages.
    const FAVICON = readFileSync(new URL("../public/favicon.svg", import.meta.url), "utf8");
    expect(FAVICON).toContain("<svg");
    expect(FAVICON).toContain("HX");
  });

  it("does not hide the purpose behind animations or scripts", () => {
    // The purpose must be plain server-rendered HTML, not gated behind
    // opacity/scroll-triggered reveals (a common Google review failure).
    expect(HOME_HTML).not.toMatch(/opacity\s*:\s*0/);
    expect(HOME_HTML).not.toContain("IntersectionObserver");
    // The first-screen hero text must state what the app does in raw HTML.
    const hero = HOME_HTML.match(/<section class="hero">([\s\S]*?)<\/section>/)?.[1] ?? "";
    expect(hero).toContain("集中管理");
    expect(hero).toContain("验证码");
  });

  it("allows search engines and Google's verifier to crawl the site", () => {
    expect(ROBOTS_TXT).toContain("User-agent: *");
    expect(ROBOTS_TXT).toContain("Allow: /");
    expect(ROBOTS_TXT).not.toContain("Disallow: /");
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
