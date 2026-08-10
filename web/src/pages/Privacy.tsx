import React, { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { BrandLayout } from "./impl/brand/BrandLayout";
import { type BrandLang, brandDicts, privacyPath } from "./impl/brand/i18n";
import { LegalSections } from "./impl/brand/LegalSections";
import { PRIVACY_EN_SECTIONS, PRIVACY_ZH_SECTIONS } from "./impl/brand/privacyContent";

interface PrivacyProps {
  lang: BrandLang;
}

const CONTACT_LABELS: Record<BrandLang, string> = {
  zh: "如果您对本政策或数据相关事宜有任何疑问，请通过以下邮箱与我们联系：",
  en: "If you have any questions about this policy or your data, contact us at:",
};

export const Privacy: React.FC<PrivacyProps> = ({ lang }) => {
  const navigate = useNavigate();

  useEffect(() => {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  }, [lang]);

  const sections = lang === "zh" ? PRIVACY_ZH_SECTIONS : PRIVACY_EN_SECTIONS;
  const dict = brandDicts[lang];
  const onLangChange = (next: BrandLang): void => {
    navigate(privacyPath(next));
  };

  return (
    <BrandLayout
      dict={dict}
      lang={lang}
      onLangChange={onLangChange}
      title={lang === "zh" ? "隐私政策 · HX-Email" : "Privacy Policy · HX-Email"}
      showFeaturesLink={false}
    >
      <main className="mx-auto max-w-[860px] px-6 py-12">
        <h1 className="mb-2 text-[34px] text-gh-text">
          {lang === "zh" ? "隐私政策" : "Privacy Policy"}
        </h1>
        <p className="mb-10 text-sm text-gh-text-muted">
          {lang === "zh" ? "生效日期：2026 年 8 月 10 日" : "Effective date: August 10, 2026"}
        </p>
        <div className="text-gh-text-muted">
          <LegalSections sections={sections} contactLabel={CONTACT_LABELS[lang]} />
        </div>
      </main>
    </BrandLayout>
  );
};
