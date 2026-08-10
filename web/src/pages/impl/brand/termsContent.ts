import type { LegalSection } from "./privacyContent";

export const TERMS_ZH_SECTIONS: LegalSection[] = [
  {
    heading: "1. 服务说明",
    paragraphs: ["本服务由您自行部署和运行。其核心功能包括："],
    list: [
      "集中管理多个邮箱账号、临时邮箱与平台账号绑定关系；",
      "自动收取邮件、识别并高亮展示邮件中的验证码；",
      "按您的配置发送、转发邮件并执行自动化任务与通知；",
      "提供实例备份、导出、导入与恢复功能。",
    ],
    highlight:
      "自托管提示：本服务是自托管软件，由部署方（您或为您提供服务的运营者）负责服务器的运行、维护与安全。",
  },
  {
    heading: "2. 账户与使用",
    list: [
      "您应妥善保管账户口令与邮箱凭据，并对账户下发生的活动负责；",
      "您应仅使用本服务处理您有权访问的邮箱与数据；",
      "请勿将本服务用于发送垃圾邮件、欺诈、侵犯他人权益或违反适用法律的活动；",
      "部署方可以随时关闭注册、调整访问权限或终止违规账户。",
    ],
  },
  {
    heading: "3. 用户责任",
    paragraphs: [
      "您负责确保所配置的邮箱服务器、凭据与外部服务（SMTP、IMAP、Telegram、Webhook 等）属于您或您已获授权使用，并承担因使用这些外部服务产生的费用与后果。请妥善保管凭据，避免泄露。",
    ],
  },
  {
    heading: "4. 数据与隐私",
    paragraphs: [
      "本服务如何处理您的数据，详见我们的隐私政策。本服务为自托管：数据默认仅存储于您自己的服务器，不向第三方出售或共享。",
    ],
  },
  {
    heading: "5. 第三方服务",
    paragraphs: [
      "本服务在与您配置的外部服务（邮箱服务器、消息通知渠道等）交互时，将按照您的配置向对应服务传输必要的数据。该等交互受第三方服务自身条款与政策的约束，我们不对第三方服务的行为负责。",
    ],
  },
  {
    heading: "6. 免责声明",
    paragraphs: [
      "本服务按“现状”提供，不附带任何明示或默示的保证。在适用法律允许的最大范围内，我们不对因使用或无法使用本服务、数据丢失、邮件发送或接收失败、验证码识别错误等造成的直接或间接损失承担责任。",
    ],
  },
  {
    heading: "7. 服务可用性与变更",
    paragraphs: [
      "本服务可能因部署方维护、升级、网络故障或不可抗力而间歇性不可用。我们可能随时更新、调整或终止本服务的部分功能，并尽力提前公告重大变更。",
    ],
  },
  {
    heading: "8. 条款变更",
    paragraphs: [
      "本条款可能随服务功能的变化而更新。更新后我们会修改本页顶部的“生效日期”，继续使用本服务即视为接受更新后的条款。",
    ],
  },
  {
    heading: "9. 联系我们",
  },
];

export const TERMS_EN_SECTIONS: LegalSection[] = [
  {
    heading: "1. Service Description",
    paragraphs: ["The Service is deployed and operated by you. Its core features include:"],
    list: [
      "Centrally managing multiple mailbox accounts, temp mailboxes and platform bindings;",
      "Automatically fetching mail and detecting and highlighting verification codes;",
      "Sending and forwarding mail and running automation tasks and notifications according to your configuration;",
      "Providing instance backup, export, import and restore features.",
    ],
    highlight:
      "Self-hosting notice: this is self-hosted software. The deployer (you or the operator providing the service to you) is responsible for running, maintaining and securing the server.",
  },
  {
    heading: "2. Accounts and Use",
    list: [
      "You must keep your account passwords and mailbox credentials safe and are responsible for activity under your account;",
      "You may only use the Service to process mailboxes and data you are authorized to access;",
      "Do not use the Service for spam, fraud, infringing on others' rights or any activity that violates applicable law;",
      "The deployer may close registration, adjust access permissions or terminate violating accounts at any time.",
    ],
  },
  {
    heading: "3. User Responsibilities",
    paragraphs: [
      "You are responsible for ensuring that the mail servers, credentials and external services (SMTP, IMAP, Telegram, Webhook, etc.) you configure belong to you or that you are authorized to use them, and you bear the costs and consequences of using those external services. Keep your credentials secure and avoid leaking them.",
    ],
  },
  {
    heading: "4. Data and Privacy",
    paragraphs: [
      "How the Service handles your data is described in our Privacy Policy. The Service is self-hosted: by default your data is stored only on your own server and is never sold or shared with third parties.",
    ],
  },
  {
    heading: "5. Third-Party Services",
    paragraphs: [
      "When the Service interacts with external services you configure (mail servers, notification channels, etc.), it transmits only the data necessary for that interaction, according to your configuration. Such interaction is governed by the third-party services' own terms and policies; we are not responsible for their behavior.",
    ],
  },
  {
    heading: "6. Disclaimer",
    paragraphs: [
      'The Service is provided "as is" without any express or implied warranty. To the fullest extent permitted by applicable law, we are not liable for any direct or indirect loss arising from the use of or inability to use the Service, data loss, failed mail sending or receiving, or incorrect verification-code recognition.',
    ],
  },
  {
    heading: "7. Service Availability and Changes",
    paragraphs: [
      "The Service may be intermittently unavailable due to deployer maintenance, upgrades, network failures or force majeure. We may update, adjust or discontinue parts of the Service at any time and will make reasonable efforts to announce material changes in advance.",
    ],
  },
  {
    heading: "8. Changes to These Terms",
    paragraphs: [
      "These terms may be updated as the Service evolves. Updates are reflected in the effective date at the top of this page. Continuing to use the Service after an update constitutes acceptance of the updated terms.",
    ],
  },
  {
    heading: "9. Contact Us",
  },
];
