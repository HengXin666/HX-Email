import React from "react";
import { BrandLayout } from "./impl/brand/BrandLayout";
import { LegalSections } from "./impl/brand/LegalSections";
import { TERMS_ZH_SECTIONS } from "./impl/brand/termsContent";
import { useBrandLang } from "./impl/brand/useBrandLang";

export const Terms: React.FC = () => {
  const { lang, dict, setLang } = useBrandLang();

  return (
    <BrandLayout
      dict={dict}
      lang={lang}
      onLangChange={setLang}
      title="服务条款 · HX-Email"
      showLangSwitch={false}
      showFeaturesLink={false}
    >
      <main className="mx-auto max-w-[860px] px-6 py-12">
        <h1 className="mb-2 text-[34px] text-gh-text">服务条款</h1>
        <p className="mb-10 text-sm text-gh-text-muted">生效日期：2026 年 8 月 10 日</p>
        <p className="mb-3.5 text-gh-text-muted">
          HX-Email（以下简称“本服务”）是一个自托管（self-hosted）的多邮箱统一管理平台，用于集中管理邮箱账号、临时邮箱与平台绑定，并支持验证码自动读取、邮件收发与自动化通知等能力。使用本服务即表示您同意本条款；如不同意，请停止使用。
        </p>
        <div className="text-gh-text-muted">
          <LegalSections
            sections={TERMS_ZH_SECTIONS}
            contactLabel="如果您对本条款有任何疑问，请通过以下邮箱与我们联系："
          />
        </div>
      </main>
    </BrandLayout>
  );
};
