import { readFileSync } from "node:fs";

import { fireEvent, render, screen, within } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { Home } from "./pages/Home";
import { Privacy } from "./pages/Privacy";
import { Terms } from "./pages/Terms";

const CONTACT_EMAIL = "loli@woa.qzz.io";
const INDEX_HTML = readFileSync("index.html", "utf8");
const MANIFEST = JSON.parse(readFileSync("public/manifest.webmanifest", "utf8")) as {
  name: string;
  short_name: string;
  icons: Array<{ src: string; sizes: string; type: string }>;
};

const renderPage = (path: string, page: React.ReactNode) =>
  render(<MemoryRouter initialEntries={[path]}>{page}</MemoryRouter>);

const expectHeading = (name: string | RegExp): void => {
  expect(screen.getAllByRole("heading", { name })).not.toHaveLength(0);
};

afterEach(() => {
  window.localStorage.clear();
});

describe("React brand pages (Google OAuth brand verification)", () => {
  it("renders a genuine landing page for the application", () => {
    renderPage("/home", <Home />);
    // The homepage has to state what the application is for.
    expect(screen.getAllByText(/HX-Email/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/unifies all your mailbox accounts/i)).not.toHaveLength(0);
    expect(screen.getAllByText(/verification codes/i)).not.toHaveLength(0);
    // The OAuth consent-screen app name must match the homepage brand name.
    expect(screen.queryByText(/HX-EMail/)).not.toBeInTheDocument();
    // The page must link back into the real app and to the legal pages.
    const consoleLinks = screen.getAllByRole("link", { name: "Open Console" });
    expect(consoleLinks.some((link) => link.getAttribute("href") === "/login")).toBe(true);
    expect(screen.getByRole("link", { name: "View Privacy Policy" })).toHaveAttribute(
      "href",
      "/privacy",
    );
    const privacyLinks = screen.getAllByRole("link", { name: "Privacy Policy" });
    expect(privacyLinks.some((link) => link.getAttribute("href") === "/privacy")).toBe(true);
    const termsLinks = screen.getAllByRole("link", { name: "Terms of Service" });
    expect(termsLinks.some((link) => link.getAttribute("href") === "/terms")).toBe(true);
    // SVG icons replace text emoji on the feature cards.
    expect(screen.getByText("Core Features")).toBeInTheDocument();
    expect(screen.getByText("Unified Account Management")).toBeInTheDocument();
    expect(document.querySelectorAll("svg").length).toBeGreaterThan(0);
    // A section that transparently explains why the app requests user data.
    expect(screen.getByText("Why HX-Email Needs Your Data")).toBeInTheDocument();
    expect(screen.getByText("Transparent · Minimal")).toBeInTheDocument();
  });

  it("switches between Chinese and English versions of the homepage", () => {
    renderPage("/home", <Home />);
    expect(screen.getByText("Core Features")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "中文" }));
    expect(screen.getByText("核心功能")).toBeInTheDocument();
    expect(screen.getByText("多账号统一管理")).toBeInTheDocument();
    expect(screen.getByText("为什么 HX-Email 需要您的数据")).toBeInTheDocument();
    expect(screen.queryByText("Core Features")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "EN" }));
    expect(screen.getByText("Core Features")).toBeInTheDocument();
  });

  it("pins the app identity consistently across every extractable field", () => {
    // Brand name must match the OAuth consent-screen name "HX-Email" exactly.
    expect(INDEX_HTML).toContain("<title>");
    expect(INDEX_HTML).toContain('rel="icon"');
    expect(INDEX_HTML).toContain('href="/icon-192.png"');
    expect(INDEX_HTML).toContain("HX-Email");
    expect(INDEX_HTML).not.toContain("HX-EMail");
    expect(INDEX_HTML).toContain('<div id="root"></div>');
    // Structured data describing the application.
    const ldJson =
      INDEX_HTML.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/)?.[1] ?? "";
    expect(JSON.parse(ldJson)).toMatchObject({
      "@type": "SoftwareApplication",
      name: "HX-Email",
    });
    expect(MANIFEST.name).toBe("HX-Email");
    expect(MANIFEST.short_name).toBe("HX-Email");
    // The icon PNG files exist next to the app shell.
    const icon192 = readFileSync("public/icon-192.png");
    const icon512 = readFileSync("public/icon-512.png");
    expect(icon192.byteLength).toBeGreaterThan(100);
    expect(icon512.byteLength).toBeGreaterThan(100);
    // The raw contact email must not appear in the HTML shell Cloudflare sees;
    // it is injected client-side by React, so edge obfuscation cannot rewrite it.
    expect(INDEX_HTML).not.toContain(CONTACT_EMAIL);
  });

  it("defaults to English and follows the browser language", () => {
    // jsdom reports en-US, so the rendered homepage is English-first.
    renderPage("/home", <Home />);
    expect(screen.getByText("Core Features")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open Console" })).not.toHaveLength(0);
    // A saved manual choice wins over auto-detection.
    window.localStorage.setItem("hx-home-lang", "zh");
    renderPage("/home", <Home />);
    expect(screen.getByText("核心功能")).toBeInTheDocument();
  });

  it("covers the privacy-policy sections Google reviewers look for", () => {
    renderPage("/privacy", <Privacy />);
    expect(screen.getByRole("heading", { name: "Privacy Policy 隐私政策" })).toBeInTheDocument();
    expect(screen.getByText(/Effective date 生效日期/)).toBeInTheDocument();
    // English sections, read by Google's reviewer.
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
      expectHeading(new RegExp(section));
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
      expectHeading(new RegExp(section));
    }
    // Explicit disclosures Google's privacy-policy review requires.
    const body = screen.getByRole("main");
    expect(within(body).getAllByText(/https:\/\/mail\.google\.com\//)).not.toHaveLength(0);
    expect(within(body).getAllByText(/do not sell/i)).not.toHaveLength(0);
    expect(within(body).getAllByText(/targeted advertising/i)).not.toHaveLength(0);
    expect(within(body).getAllByText(/train AI/i)).not.toHaveLength(0);
    expect(within(body).getAllByText(/encrypted when stored/i)).not.toHaveLength(0);
    // Contact email is rendered client-side (safe from edge obfuscation).
    expect(screen.getAllByText(CONTACT_EMAIL)).not.toHaveLength(0);
  });

  it("provides a public terms-of-service page linked from the homepage", () => {
    renderPage("/terms", <Terms />);
    expect(screen.getByRole("heading", { name: "服务条款" })).toBeInTheDocument();
    expect(screen.getAllByText(/生效日期/)).not.toHaveLength(0);
    for (const section of ["服务说明", "账户与使用", "用户责任", "免责声明", "联系我们"]) {
      expectHeading(new RegExp(section));
    }
    expect(screen.getAllByText(CONTACT_EMAIL)).not.toHaveLength(0);
    const homeLinks = screen.getAllByRole("link", { name: "Home" });
    expect(homeLinks.some((link) => link.getAttribute("href") === "/home")).toBe(true);
    const privacyLinks = screen.getAllByRole("link", { name: "Privacy Policy" });
    expect(privacyLinks.some((link) => link.getAttribute("href") === "/privacy")).toBe(true);
  });
});
