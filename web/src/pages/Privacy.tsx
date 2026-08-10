import React from "react";
import { BrandLayout } from "./impl/brand/BrandLayout";
import { LegalSections } from "./impl/brand/LegalSections";
import { PRIVACY_EN_SECTIONS, PRIVACY_ZH_SECTIONS } from "./impl/brand/privacyContent";
import { useBrandLang } from "./impl/brand/useBrandLang";

export const Privacy: React.FC = () => {
  const { lang, dict, setLang } = useBrandLang();

  return (
    <BrandLayout
      dict={dict}
      lang={lang}
      onLangChange={setLang}
      title="Privacy Policy 隐私政策 · HX-Email"
      showLangSwitch={false}
      showFeaturesLink={false}
    >
      <main className="mx-auto max-w-[860px] px-6 py-12">
        <h1 className="mb-2 text-[34px] text-gh-text">Privacy Policy 隐私政策</h1>
        <p className="mb-10 text-sm text-gh-text-muted">
          Effective date 生效日期：August 10, 2026 · 2026 年 8 月 10 日
        </p>
        <p>
          <span className="mb-6 inline-block rounded-full border border-gh-border bg-gh-canvas-subtle px-3 py-0.5 text-[13px] text-gh-text-muted">
            English version below · 英文版见下；中文版本见页面底部
          </span>
        </p>
        <div className="text-gh-text-muted">
          <LegalSections
            sections={PRIVACY_EN_SECTIONS}
            contactLabel="If you have any questions about this policy or your data, contact us at:"
          />
        </div>

        <div className="mt-16 border-t border-gh-border-muted pt-2">
          <h1 className="mb-2 mt-8 text-[28px] text-gh-text">隐私政策（中文版）</h1>
          <p className="mb-10 text-sm text-gh-text-muted">生效日期：2026 年 8 月 10 日</p>
          <div className="text-gh-text-muted">
            <LegalSections
              sections={PRIVACY_ZH_SECTIONS}
              contactLabel="如果您对本政策或数据相关事宜有任何疑问，请通过以下邮箱与我们联系："
            />
          </div>
        </div>
      </main>
    </BrandLayout>
  );
};
