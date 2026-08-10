import { useEffect, useState } from "react";
import { type BrandDict, type BrandLang, brandDicts } from "./i18n";

const LANG_KEY = "hx-home-lang";

function detectBrandLang(): BrandLang {
  const nav = navigator.language || (navigator.languages?.[0] ?? "en");
  return nav.toLowerCase().startsWith("zh") ? "zh" : "en";
}

function readStoredLang(): BrandLang | null {
  try {
    const saved = window.localStorage?.getItem(LANG_KEY);
    return saved === "zh" || saved === "en" ? saved : null;
  } catch {
    return null;
  }
}

export function useBrandLang(): {
  lang: BrandLang;
  dict: BrandDict;
  setLang: (lang: BrandLang) => void;
} {
  const [lang, setLangState] = useState<BrandLang>(() => readStoredLang() ?? detectBrandLang());

  useEffect(() => {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  }, [lang]);

  const setLang = (next: BrandLang): void => {
    setLangState(next);
    try {
      window.localStorage?.setItem(LANG_KEY, next);
    } catch {}
  };

  return { lang, dict: brandDicts[lang], setLang };
}
