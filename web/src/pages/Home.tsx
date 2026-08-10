import { Inbox, KeyRound, Link2, Mailbox, ShieldCheck, Zap } from "lucide-react";
import React from "react";
import { Link } from "react-router-dom";
import { BrandLayout } from "./impl/brand/BrandLayout";
import { type BrandDict, type BrandLang, privacyPath } from "./impl/brand/i18n";
import { useBrandLang } from "./impl/brand/useBrandLang";

interface FeatureCardProps {
  icon: React.ReactNode;
  title: string;
  desc: string;
}

const FeatureCard: React.FC<FeatureCardProps> = ({ icon, title, desc }) => (
  <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle p-6 transition hover:-translate-y-0.5 hover:border-gh-success/40">
    <div className="mb-4 inline-flex h-[42px] w-[42px] items-center justify-center rounded-[10px] bg-gh-accent-muted text-gh-accent">
      {icon}
    </div>
    <h3 className="mb-2 text-[17px] text-gh-text">{title}</h3>
    <p className="text-sm leading-relaxed text-gh-text-muted">{desc}</p>
  </div>
);

export const Home: React.FC = () => {
  const { lang, dict, setLang } = useBrandLang();

  const features: Array<{ icon: React.ReactNode; title: string; desc: string }> = [
    { icon: <Inbox size={20} strokeWidth={1.8} />, title: dict.f1Title, desc: dict.f1Desc },
    { icon: <KeyRound size={20} strokeWidth={1.8} />, title: dict.f2Title, desc: dict.f2Desc },
    { icon: <Zap size={20} strokeWidth={1.8} />, title: dict.f3Title, desc: dict.f3Desc },
    { icon: <Link2 size={20} strokeWidth={1.8} />, title: dict.f4Title, desc: dict.f4Desc },
    { icon: <Mailbox size={20} strokeWidth={1.8} />, title: dict.f5Title, desc: dict.f5Desc },
    { icon: <ShieldCheck size={20} strokeWidth={1.8} />, title: dict.f6Title, desc: dict.f6Desc },
  ];

  return (
    <BrandLayout dict={dict} lang={lang} onLangChange={setLang}>
      <main>
        <section className="bg-[radial-gradient(600px_260px_at_50%_-60px,rgba(31,111,235,0.15),transparent),linear-gradient(180deg,#0d1117_0%,#0a0e14_100%)] px-6 pb-20 pt-24 text-center">
          <div className="mx-auto max-w-[1080px]">
            <span className="mb-6 inline-flex items-center gap-2 rounded-full border border-gh-border bg-gh-canvas-subtle px-3.5 py-1.5 text-[13px] text-gh-text-muted">
              {dict.heroEyebrow}
            </span>
            <h1 className="mb-4 text-[clamp(44px,8vw,72px)] font-extrabold leading-[1.08] tracking-tight text-gh-text">
              HX-Email<span className="text-gh-success">.</span>
            </h1>
            <p className="mx-auto mb-9 max-w-[680px] text-lg text-gh-text-muted">
              {dict.heroSubtitle}
            </p>
            <p className="mx-auto mt-5 max-w-[720px] text-sm leading-7 text-gh-text-muted">
              {dict.heroGoogle}
            </p>
            <div className="mt-9 flex flex-wrap justify-center gap-3.5">
              <Link
                to="/login"
                className="inline-block rounded-lg border border-transparent bg-gh-success px-7 py-3 text-[15px] font-semibold text-white transition hover:brightness-110"
              >
                {dict.heroCta}
              </Link>
              <Link
                to={privacyPath(lang)}
                className="inline-block rounded-lg border border-gh-border bg-gh-canvas-subtle px-7 py-3 text-[15px] font-semibold text-gh-text transition hover:brightness-110"
              >
                {dict.heroPrivacy}
              </Link>
            </div>
          </div>
        </section>

        <section id="features" className="border-t border-gh-border-muted px-6 py-16">
          <div className="mx-auto max-w-[1080px]">
            <h2 className="mb-2.5 text-3xl font-bold tracking-tight text-gh-text">
              {dict.featuresTitle}
            </h2>
            <p className="mb-10 max-w-[640px] text-gh-text-muted">{dict.featuresDesc}</p>
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {features.map((feature) => (
                <FeatureCard key={feature.title} {...feature} />
              ))}
            </div>
          </div>
        </section>

        <section id="data" className="border-t border-gh-border-muted px-6 py-16">
          <div className="mx-auto max-w-[1080px]">
            <h2 className="mb-2.5 text-3xl font-bold tracking-tight text-gh-text">
              {dict.dataTitle}
            </h2>
            <p className="mb-10 max-w-[640px] text-gh-text-muted">{dict.dataDesc}</p>
            <div className="flex items-start gap-4 rounded-xl border border-gh-border bg-gh-canvas-subtle p-7">
              <span className="shrink-0 rounded-full border border-gh-success/30 bg-gh-success/10 px-3 py-1 text-xs font-semibold text-gh-success">
                {dict.dataBadge}
              </span>
              <div>
                <p className="text-sm text-gh-text-muted">{dict.dataP1}</p>
                <ul className="mt-2.5 list-disc pl-5 text-sm text-gh-text-muted">
                  <li>{dict.dataL1}</li>
                  <li>{dict.dataL2}</li>
                  <li>{dict.dataL3}</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section id="how" className="border-t border-gh-border-muted px-6 py-16">
          <div className="mx-auto max-w-[1080px]">
            <h2 className="mb-2.5 text-3xl font-bold tracking-tight text-gh-text">
              {dict.howTitle}
            </h2>
            <p className="mb-10 max-w-[640px] text-gh-text-muted">{dict.howDesc}</p>
            <div className="grid gap-5 sm:grid-cols-3">
              {[
                { num: "1", title: dict.howS1Title, desc: dict.howS1Desc },
                { num: "2", title: dict.howS2Title, desc: dict.howS2Desc },
                { num: "3", title: dict.howS3Title, desc: dict.howS3Desc },
              ].map((step) => (
                <div
                  key={step.num}
                  className="relative rounded-xl border border-gh-border bg-gh-canvas-subtle p-6"
                >
                  <div className="mb-2.5 text-[28px] font-extrabold text-gh-success">
                    {step.num}
                  </div>
                  <h3 className="mb-2 text-base text-gh-text">{step.title}</h3>
                  <p className="text-sm text-gh-text-muted">{step.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="privacy" className="border-t border-gh-border-muted px-6 py-16">
          <div className="mx-auto max-w-[1080px]">
            <h2 className="mb-2.5 text-3xl font-bold tracking-tight text-gh-text">
              {dict.privacyTitle}
            </h2>
            <p className="mb-10 max-w-[640px] text-gh-text-muted">{dict.privacyDesc}</p>
            <div className="flex items-start gap-4 rounded-xl border border-gh-border bg-gh-canvas-subtle p-7">
              <span className="shrink-0 rounded-full border border-gh-success/30 bg-gh-success/10 px-3 py-1 text-xs font-semibold text-gh-success">
                {dict.privacyBadge}
              </span>
              <p className="text-sm text-gh-text-muted">
                {dict.privacyP}{" "}
                <Link to={privacyPath(lang)} className="text-gh-accent transition hover:underline">
                  {dict.privacyLink}
                </Link>
              </p>
            </div>
          </div>
        </section>
      </main>
    </BrandLayout>
  );
};
