import React, { type ReactNode, useEffect } from "react";
import { Link } from "react-router-dom";
import { type BrandDict, type BrandLang, CONTACT_EMAIL } from "./i18n";

interface BrandLayoutProps {
  dict: BrandDict;
  lang: BrandLang;
  onLangChange: (lang: BrandLang) => void;
  title?: string;
  showLangSwitch?: boolean;
  showFeaturesLink?: boolean;
  children: ReactNode;
}

const LangSwitch: React.FC<{
  lang: BrandLang;
  onLangChange: (lang: BrandLang) => void;
}> = ({ lang, onLangChange }) => (
  <span className="flex items-center gap-0.5 rounded-full border border-gh-border p-0.5 text-xs">
    <button
      type="button"
      onClick={() => onLangChange("zh")}
      aria-pressed={lang === "zh"}
      className={`rounded-full px-2.5 py-1 text-xs transition ${lang === "zh" ? "bg-gh-accent text-white" : "text-gh-text-muted hover:text-gh-text"}`}
    >
      中文
    </button>
    <button
      type="button"
      onClick={() => onLangChange("en")}
      aria-pressed={lang === "en"}
      className={`rounded-full px-2.5 py-1 text-xs transition ${lang === "en" ? "bg-gh-accent text-white" : "text-gh-text-muted hover:text-gh-text"}`}
    >
      EN
    </button>
  </span>
);

export const BrandLayout: React.FC<BrandLayoutProps> = ({
  dict,
  lang,
  onLangChange,
  title = "HX-Email",
  showLangSwitch = true,
  showFeaturesLink = true,
  children,
}) => {
  useEffect(() => {
    document.title = title;
    const meta = document.querySelector('meta[name="description"]');
    if (meta) meta.setAttribute("content", dict.metaDescription);
  }, [title, dict.metaDescription]);

  return (
    <div className="h-screen overflow-y-auto bg-gh-canvas text-gh-text antialiased">
      <header className="sticky top-0 z-20 border-b border-gh-border-muted bg-gh-canvas-inset/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1080px] items-center justify-between gap-4 px-6">
          <Link
            to="/home"
            className="flex items-center gap-2 whitespace-nowrap text-xl font-bold tracking-wider text-gh-text"
          >
            <img className="h-7 w-7 rounded-md" src="/icon-192.png" alt="" width="28" height="28" />
            HX<span className="text-gh-success">-Email</span>
          </Link>
          <nav
            className="flex items-center gap-4 text-sm"
            aria-label={lang === "zh" ? "主导航" : "Main navigation"}
          >
            <Link to="/home" className="text-gh-text-muted transition hover:text-gh-text">
              {dict.navHome}
            </Link>
            {showFeaturesLink && (
              <a
                href="#features"
                className="hidden text-gh-text-muted transition hover:text-gh-text sm:inline"
              >
                {dict.navFeatures}
              </a>
            )}
            <Link to="/privacy" className="text-gh-text-muted transition hover:text-gh-text">
              {dict.navPrivacy}
            </Link>
            <Link to="/terms" className="text-gh-text-muted transition hover:text-gh-text">
              {dict.navTerms}
            </Link>
            <Link
              to="/login"
              className="hidden text-gh-text-muted transition hover:text-gh-text sm:inline"
            >
              {dict.navConsole}
            </Link>
            {showLangSwitch && <LangSwitch lang={lang} onLangChange={onLangChange} />}
          </nav>
        </div>
      </header>
      {children}
      <footer className="border-t border-gh-border-muted py-9">
        <div className="mx-auto flex max-w-[1080px] flex-wrap items-center justify-between gap-3 px-6 text-[13px] text-gh-text-secondary">
          <span>© {new Date().getFullYear()} HX-Email. All rights reserved.</span>
          <span className="flex flex-wrap gap-4">
            <Link to="/home" className="text-gh-text-muted transition hover:text-gh-text">
              {dict.footerHome}
            </Link>
            <Link to="/privacy" className="text-gh-text-muted transition hover:text-gh-text">
              {dict.footerPrivacy}
            </Link>
            <Link to="/terms" className="text-gh-text-muted transition hover:text-gh-text">
              {dict.footerTerms}
            </Link>
            <a
              href={`mailto:${CONTACT_EMAIL}`}
              className="text-gh-text-muted transition hover:text-gh-text"
            >
              {CONTACT_EMAIL}
            </a>
          </span>
        </div>
      </footer>
    </div>
  );
};
