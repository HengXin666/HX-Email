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
    expect(HOME_HTML).toContain('<html lang="en">');
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
    expect(HOME_HTML).toContain(
      '<link rel="icon" type="image/png" sizes="192x192" href="/icon-192.png" />',
    );
    expect(HOME_HTML).toContain('<link rel="apple-touch-icon" href="/icon-192.png" />');
    expect(HOME_HTML).toContain('src="/icon-192.png"');
    expect(MANIFEST.icons).toEqual([
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ]);
    // The icon PNG files themselves exist next to the brand pages.
    const icon192 = readFileSync(new URL("../public/icon-192.png", import.meta.url));
    const icon512 = readFileSync(new URL("../public/icon-512.png", import.meta.url));
    expect(icon192.subarray(0, 4)).toEqual(Buffer.from([0x89, 0x50, 0x4e, 0x47]));
    expect(icon512.subarray(0, 4)).toEqual(Buffer.from([0x89, 0x50, 0x4e, 0x47]));
  });

  it("does not hide the purpose behind animations or scripts", () => {
    // The purpose must be plain server-rendered HTML, not gated behind
    // opacity/scroll-triggered reveals (a common Google review failure).
    expect(HOME_HTML).not.toMatch(/opacity\s*:\s*0/);
    expect(HOME_HTML).not.toContain("IntersectionObserver");
    // The first-screen hero text must state what the app does in raw HTML.
    const hero = HOME_HTML.match(/<section class="hero">([\s\S]*?)<\/section>/)?.[1] ?? "";
    expect(hero).toContain("self-hosted email management application");
    expect(hero).toContain("auto-read verification codes");
  });

  it("allows search engines and Google's verifier to crawl the site", () => {
    expect(ROBOTS_TXT).toContain("User-agent: *");
    expect(ROBOTS_TXT).toContain("Allow: /");
    expect(ROBOTS_TXT).not.toContain("Disallow: /");
  });

  it("shows the app name prominently and supports bilingual content", () => {
    // The app name must be the visible H1 heading, not just a side mention.
    // Plain text with no nested spans, so any extractor reads exactly "HX-Email".
    expect(HOME_HTML).toContain("<h1>HX-Email</h1>");
    expect(HOME_HTML).not.toMatch(/<h1[^>]*>[^<]*<span/);
    // Bilingual switcher with zh-CN default and an English option.
    expect(HOME_HTML).toContain('data-lang="zh"');
    expect(HOME_HTML).toContain('data-lang="en"');
    expect(HOME_HTML).toContain("hx-home-lang");
    expect(HOME_HTML).toContain('"nav.console": "Open Console"');
    // A section that transparently explains why the app requests user data.
    expect(HOME_HTML).toContain('id="data"');
    expect(HOME_HTML).toContain("为什么 HX-Email 需要您的数据");
    expect(HOME_HTML).toContain("Why HX-Email Needs Your Data");
    // The purpose must also be stated in English in the server-rendered HTML,
    // so keyword-based reviewers see it regardless of language or JS.
    expect(HOME_HTML).toContain("HX-Email is a self-hosted email management application");
    // The JS language switcher must never rewrite the exact title.
    expect(HOME_HTML).toContain('document.title = "HX-Email";');
  });

  it("defaults to English and follows the browser language", () => {
    // Static HTML (the no-JS view Google's crawler reads) is English-first.
    expect(HOME_HTML).toContain('<html lang="en">');
    expect(HOME_HTML).toContain('class="active" aria-pressed="true">EN');
    // Browser language detection: zh* -> Chinese, everything else -> English.
    expect(HOME_HTML).toContain("navigator.language");
    expect(HOME_HTML).toContain('indexOf("zh") === 0 ? "zh" : "en"');
    // A saved manual choice still wins over auto-detection.
    expect(HOME_HTML).toContain('saved === "zh" || saved === "en" ? saved : detectLang()');
    expect(HOME_HTML).toContain("hx-home-lang");
    // Static English purpose is present without any JS.
    expect(HOME_HTML).toContain("HX-Email unifies all your mailbox accounts");
    // The privacy-policy link survives the language switch (nested element kept).
    expect(HOME_HTML).toContain('data-i18n="privacy.p">HX-Email is a self-hosted service');
    expect(HOME_HTML).toContain('data-i18n="privacy.link">Privacy Policy');
  });

  it("covers the privacy-policy sections Google reviewers look for", () => {
    expect(PRIVACY_HTML).toContain("<title>Privacy Policy");
    expect(PRIVACY_HTML).toContain("生效日期");
    expect(PRIVACY_HTML).toContain("Effective date");
    // English sections, read by Google's reviewer without any language/JS assumption.
    for (const section of [
      "Information We Collect",
      "How We Use Information",
      "Google User Data",
      "Storage",
      "Sharing and Disclosure",
      "Data Security",
      "Data Retention and Deletion",
      "Cookies and Tracking",
      "Your Rights",
      "Policy Updates",
      "Contact Us",
    ]) {
      expect(PRIVACY_HTML).toContain(section);
    }
    // Chinese version stays available for zh users.
    for (const section of [
      "我们收集的信息",
      "数据的存储",
      "数据的共享与披露",
      "数据安全",
      "数据保留与删除",
      "Cookie",
      "您的权利",
      "联系我们",
      "Google 用户数据",
    ]) {
      expect(PRIVACY_HTML).toContain(section);
    }
    // Explicit disclosures Google's privacy-policy review requires.
    expect(PRIVACY_HTML).toContain("https://mail.google.com/");
    expect(PRIVACY_HTML).toContain("not</strong> sell");
    expect(PRIVACY_HTML).toContain("targeted advertising");
    expect(PRIVACY_HTML).toContain("train AI");
    expect(PRIVACY_HTML).toContain("encrypted when stored");
    // Contact email is entity-encoded so Cloudflare edge obfuscation cannot
    // rewrite it into a "[email protected]" placeholder for the reviewer.
    expect(PRIVACY_HTML).toContain("loli&#64;woa&#46;qzz&#46;io");
    expect(PRIVACY_HTML).not.toContain("mailto:loli@woa.qzz.io");
    expect(PRIVACY_HTML).not.toContain("[email");
    expect(PRIVACY_HTML).toContain('href="/home.html"');
  });

  it("explains Google-data usage transparently on the homepage", () => {
    // The homepage must state why the app requests user data (Google OAuth / Gmail).
    expect(HOME_HTML).toContain('class="google-note"');
    expect(HOME_HTML).toContain("Google Sign-In");
    expect(HOME_HTML).toContain("explicit consent");
    expect(HOME_HTML).toContain("Google 登录连接 Gmail");
    // No raw email literal that Cloudflare could obfuscate on the brand pages.
    expect(HOME_HTML).not.toContain("mailto:loli@woa.qzz.io");
    expect(TERMS_HTML).not.toContain("mailto:loli@woa.qzz.io");
    expect(TERMS_HTML).toContain("loli&#64;woa&#46;qzz&#46;io");
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
