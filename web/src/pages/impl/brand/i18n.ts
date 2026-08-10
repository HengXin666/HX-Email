export type BrandLang = "zh" | "en";

export interface BrandDict {
  navHome: string;
  navFeatures: string;
  navPrivacy: string;
  navTerms: string;
  navConsole: string;
  heroEyebrow: string;
  heroSubtitle: string;
  heroCta: string;
  heroGoogle: string;
  heroPrivacy: string;
  featuresTitle: string;
  featuresDesc: string;
  f1Title: string;
  f1Desc: string;
  f2Title: string;
  f2Desc: string;
  f3Title: string;
  f3Desc: string;
  f4Title: string;
  f4Desc: string;
  f5Title: string;
  f5Desc: string;
  f6Title: string;
  f6Desc: string;
  dataTitle: string;
  dataDesc: string;
  dataBadge: string;
  dataP1: string;
  dataL1: string;
  dataL2: string;
  dataL3: string;
  howTitle: string;
  howDesc: string;
  howS1Title: string;
  howS1Desc: string;
  howS2Title: string;
  howS2Desc: string;
  howS3Title: string;
  howS3Desc: string;
  privacyTitle: string;
  privacyDesc: string;
  privacyBadge: string;
  privacyP: string;
  privacyLink: string;
  footerHome: string;
  footerPrivacy: string;
  footerTerms: string;
  metaDescription: string;
}

const zhDict: BrandDict = {
  navHome: "首页",
  navFeatures: "功能",
  navPrivacy: "隐私政策",
  navTerms: "服务条款",
  navConsole: "进入控制台",
  heroEyebrow: "Self-hosted · 自托管多邮箱管理平台",
  heroSubtitle:
    "HX-Email 集中管理您所有的邮箱账号、临时邮箱与平台绑定，自动读取验证码、按规则收发邮件，让多个账号的管理变得简单而高效。",
  heroCta: "进入控制台",
  heroGoogle:
    "通过 Google 登录连接 Gmail 账号时，HX-Email 仅在您明确授权后访问邮件数据，用于收取、展示、自动读取验证码以及按您的规则发送/转发邮件。数据只存储于您自托管的服务器。",
  heroPrivacy: "查看隐私政策",
  featuresTitle: "核心功能",
  featuresDesc: "面向个人与小型团队的多邮箱管理工作台，覆盖从账号管理到邮件自动化的完整流程。",
  f1Title: "多账号统一管理",
  f1Desc: "在一个界面集中管理多个邮箱账号，统一查看状态、刷新登录态与维护凭据。",
  f2Title: "验证码自动读取",
  f2Desc: "自动识别邮件中的验证码并高亮展示，配合浏览器脚本实现一键回填。",
  f3Title: "邮件自动化",
  f3Desc: "定时收取、SMTP 发送、转发，并支持 Telegram、Webhook 与自定义脚本流水线通知。",
  f4Title: "平台账号绑定",
  f4Desc: "追踪平台绑定与分组归属，随时可搜索与维护。",
  f5Title: "临时邮箱",
  f5Desc: "内置临时邮箱池，按需创建并按策略回收，保护您的主收件箱。",
  f6Title: "数据自主可控",
  f6Desc: "自托管部署，数据仅存储于您自己的服务器本地数据库，无任何第三方云依赖。",
  dataTitle: "为什么 HX-Email 需要您的数据",
  dataDesc:
    "透明披露：HX-Email 仅在您主动连接时，通过 Google 官方 OAuth 流程请求访问您的邮箱（如 Gmail / Google 账号）。",
  dataBadge: "透明 · 最小化",
  dataP1: "HX-Email 请求的邮箱数据仅用于以下目的——绝无其他用途，也不会与第三方共享：",
  dataL1: "在统一界面中收取并展示您的邮件，自动识别并高亮验证码；",
  dataL2: "按您的配置发送、转发与自动化处理邮件；",
  dataL3: "所有数据仅存于您自己的服务器，可随时解除连接或删除。",
  howTitle: "三步快速上手",
  howDesc: "从部署到自动读取验证码，只需几分钟。",
  howS1Title: "部署或登录",
  howS1Desc: "自托管部署或登录控制台，由管理员管理实例设置。",
  howS2Title: "连接邮箱",
  howS2Desc: "通过 OAuth 或 IMAP/SMTP 凭据绑定 Outlook、Gmail 等邮箱。",
  howS3Title: "自动收取与验证码",
  howS3Desc: "系统定时轮询新邮件并提取验证码，支持通知与自动化流水线。",
  privacyTitle: "数据与隐私",
  privacyDesc: "我们遵循最小化收集、透明处理与自我掌控的原则。",
  privacyBadge: "隐私友好",
  privacyP:
    "HX-Email 是自托管服务：所有数据（凭据、邮件内容、设置与日志）均存储于您自己的服务器，完全由您掌控。无广告，无第三方追踪脚本。详见",
  privacyLink: "隐私政策。",
  footerHome: "首页",
  footerPrivacy: "隐私政策",
  footerTerms: "服务条款",
  metaDescription:
    "HX-Email 统一多邮箱管理平台：集中管理邮箱账号、临时邮箱与平台绑定，自动读取验证码并按规则收发邮件。自托管，数据完全属于您。",
};

const enDict: BrandDict = {
  navHome: "Home",
  navFeatures: "Features",
  navPrivacy: "Privacy Policy",
  navTerms: "Terms of Service",
  navConsole: "Open Console",
  heroEyebrow: "Self-hosted · Unified multi-mailbox management",
  heroSubtitle:
    "HX-Email unifies all your mailbox accounts, temp mailboxes and platform bindings in one workspace: auto-read verification codes and send or forward mail on schedule — simple and efficient management of many accounts.",
  heroCta: "Open Console",
  heroGoogle:
    "When you connect a Gmail account with Google Sign-In, HX-Email accesses your mail data only after your explicit consent, to fetch and display mail, auto-read verification codes, and send or forward mail per your rules. Data stays on your self-hosted server.",
  heroPrivacy: "View Privacy Policy",
  featuresTitle: "Core Features",
  featuresDesc:
    "A multi-mailbox workbench for individuals and small teams, covering the full flow from account management to mail automation.",
  f1Title: "Unified Account Management",
  f1Desc:
    "Manage multiple mailbox accounts in one interface: check status, refresh sessions and maintain credentials.",
  f2Title: "Auto Verification Codes",
  f2Desc:
    "Automatically detect verification codes in mail and highlight them, with browser scripts for one-click fill-in.",
  f3Title: "Mail Automation",
  f3Desc:
    "Scheduled fetching, SMTP sending, forwarding, plus Telegram, Webhook and custom script pipeline notifications.",
  f4Title: "Platform Account Binding",
  f4Desc:
    "Track bindings and group membership across platforms, searchable and maintainable at any time.",
  f5Title: "Temp Mailboxes",
  f5Desc:
    "Built-in temp mailbox pool, created on demand and recycled by policy to protect your primary inbox.",
  f6Title: "Data Under Your Control",
  f6Desc:
    "Self-hosted deployment; data is stored only in your own server's local database, with no third-party cloud dependency.",
  dataTitle: "Why HX-Email Needs Your Data",
  dataDesc:
    "Transparent disclosure: HX-Email only requests access to your mailbox (e.g. Gmail / Google account) through Google's official OAuth flow when you actively connect it.",
  dataBadge: "Transparent · Minimal",
  dataP1:
    "Mailbox data requested by HX-Email is used only for the following purposes — never for anything else, and never shared with third parties:",
  dataL1:
    "Fetch and display your mail in one place, automatically detecting and highlighting verification codes;",
  dataL2: "Send, forward and automate mail according to your configuration;",
  dataL3: "All data stays on your own server and can be disconnected or deleted at any time.",
  howTitle: "Get Started in 3 Steps",
  howDesc: "From deployment to auto-read verification codes in minutes.",
  howS1Title: "Deploy or Sign In",
  howS1Desc: "Self-host a deployment or sign in to the console; admins manage instance settings.",
  howS2Title: "Connect Mailboxes",
  howS2Desc: "Bind Outlook, Gmail and other mailboxes via OAuth or IMAP/SMTP credentials.",
  howS3Title: "Auto-fetch & Codes",
  howS3Desc:
    "The system polls for new mail and extracts verification codes, with notifications and automation pipelines.",
  privacyTitle: "Data & Privacy",
  privacyDesc:
    "We follow the principles of minimal collection, transparent processing and self-control.",
  privacyBadge: "Privacy-friendly",
  privacyP:
    "HX-Email is a self-hosted service: all data (credentials, mail content, settings and logs) is stored on your own server and fully under your control. No ads, no third-party tracking scripts. See the",
  privacyLink: "Privacy Policy.",
  footerHome: "Home",
  footerPrivacy: "Privacy Policy",
  footerTerms: "Terms of Service",
  metaDescription:
    "HX-Email unified multi-mailbox management platform: centrally manage mailbox accounts, temp mailboxes and platform bindings, auto-read verification codes and send or forward mail on schedule. Self-hosted, your data stays yours.",
};

export const brandDicts: Record<BrandLang, BrandDict> = { zh: zhDict, en: enDict };

export const CONTACT_EMAIL = "loli@woa.qzz.io";

export function privacyPath(lang: BrandLang): string {
  return lang === "zh" ? "/privacy/zh" : "/privacy";
}

export function termsPath(lang: BrandLang): string {
  return lang === "zh" ? "/terms/zh" : "/terms";
}
