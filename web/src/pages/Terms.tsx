import React, { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { BrandLayout } from "./impl/brand/BrandLayout";
import { type BrandLang, brandDicts, termsPath } from "./impl/brand/i18n";
import { LegalSections } from "./impl/brand/LegalSections";
import { TERMS_EN_SECTIONS, TERMS_ZH_SECTIONS } from "./impl/brand/termsContent";

interface TermsProps {
  lang: BrandLang;
}

const CONTACT_LABELS: Record<BrandLang, string> = {
  zh: "如果您对本条款有任何疑问，请通过以下邮箱与我们联系：",
  en: "If you have any questions about these terms, contact us at:",
};

export const Terms: React.FC<TermsProps> = ({ lang }) => {
  const navigate = useNavigate();

  useEffect(() => {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  }, [lang]);

  const sections = lang === "zh" ? TERMS_ZH_SECTIONS : TERMS_EN_SECTIONS;
  const dict = brandDicts[lang];
  const onLangChange = (next: BrandLang): void => {
    navigate(termsPath(next));
  };

  return (
    <BrandLayout
      dict={dict}
      lang={lang}
      onLangChange={onLangChange}
      title={lang === "zh" ? "服务条款 · HX-Email" : "Terms of Service · HX-Email"}
      showFeaturesLink={false}
    >
      <main className="mx-auto max-w-[860px] px-6 py-12">
        <h1 className="mb-2 text-[34px] text-gh-text">
          {lang === "zh" ? "服务条款" : "Terms of Service"}
        </h1>
        <p className="mb-10 text-sm text-gh-text-muted">
          {lang === "zh" ? "生效日期：2026 年 8 月 10 日" : "Effective date: August 10, 2026"}
        </p>
        <p className="mb-3.5 text-gh-text-muted">
          {lang === "zh"
            ? "HX-Email（以下简称“本服务”）是一个自托管（self-hosted）的多邮箱统一管理平台，用于集中管理邮箱账号、临时邮箱与平台绑定，并支持验证码自动读取、邮件收发与自动化通知等能力。使用本服务即表示您同意本条款；如不同意，请停止使用。"
            : 'HX-Email ("the Service") is a self-hosted multi-mailbox management platform for centrally managing mailbox accounts, temp mailboxes and platform bindings, with support for automatic verification-code reading, sending and forwarding mail, and automation notifications. By using the Service you agree to these terms; if you do not agree, please stop using it.'}
        </p>
        <div className="text-gh-text-muted">
          <LegalSections sections={sections} contactLabel={CONTACT_LABELS[lang]} />
        </div>
      </main>
    </BrandLayout>
  );
};
