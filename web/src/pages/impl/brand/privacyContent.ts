export interface LegalSection {
  heading: string;
  paragraphs?: string[];
  list?: string[];
  highlight?: string;
}

export const PRIVACY_EN_SECTIONS: LegalSection[] = [
  {
    heading: "1. Information We Collect",
    paragraphs: [
      'HX-Email ("we", "the service") is a self-hosted email management platform. We collect only the information required to provide the features you use:',
    ],
    list: [
      "Account information: the email addresses you add, SMTP/IMAP server settings, third-party account bindings, and your login account.",
      "Mail content: messages you receive, send or forward through the service, including verification codes, bodies and attachments.",
      "Operational data: system settings, groups and labels, polling and automation configuration, and operation logs required to provide the service.",
    ],
  },
  {
    heading: "2. How We Use Information",
    paragraphs: [
      "We use the information collected only to provide the core functionality of the service, including:",
    ],
    list: [
      "Displaying and managing your mailbox accounts and platform bindings;",
      "Fetching mail, reading verification codes, and sending or forwarding mail according to your configuration;",
      "Running automation and notifications you configure (for example Telegram, Webhook, or browser notifications);",
      "Providing backup, export, import and restore features.",
    ],
  },
  {
    heading: "3. Google User Data",
    paragraphs: [
      "When you connect a Gmail account using Google OAuth, you grant HX-Email access to your Google account data solely to provide the mail features you requested. Specifically:",
    ],
    list: [
      "What we access: your Gmail messages (including content, attachments and metadata) and your Google account email address, under the scope https://mail.google.com/ together with OpenID scopes (openid email), only after you explicitly authorize the connection.",
      "How we use it: to fetch and display your mail, automatically read verification codes, and send or forward mail and run automation on your behalf — all under the rules you configure.",
      "What we do not do: we do not use Google user data for targeted advertising, selling to data brokers, determining credit-worthiness, or any purpose other than providing or improving the features you use. We do not use Google user data to develop, improve or train AI or machine learning models.",
    ],
  },
  {
    heading: "4. Storage",
    paragraphs: [
      "HX-Email is self-hosted software: all data is stored by default in a local database (SQLite) and data directory on the server you deploy, fully under your control. We (the developers) have no access to your data, and there is no central cloud database.",
    ],
    highlight:
      "Note: if you host or deploy this service for others, you act as the data controller for that instance and must comply with the data protection laws applicable to you.",
  },
  {
    heading: "5. Sharing and Disclosure",
    list: [
      "We do not sell, rent or share your data with any third party.",
      "Data is only used to connect to external services you explicitly configure: for example, sending mail to an SMTP server you specify, fetching mail from an IMAP server you specify, or delivering notifications to Telegram / Webhook addresses you specify.",
      "We do not disclose your data without your consent, except where required by law.",
    ],
  },
  {
    heading: "6. Data Security",
    list: [
      "Passwords and mailbox credentials are encrypted when stored;",
      "We recommend protecting your own server with HTTPS, strong passwords, access control and regular backups;",
      "You can export a full backup of your instance from Settings, or delete accounts and data you no longer need.",
    ],
  },
  {
    heading: "7. Data Retention and Deletion",
    paragraphs: [
      "You can delete accounts, mail or related records from the interface at any time, export or reset data, and permanently delete everything by removing the instance data directory. We retain data only as long as needed to provide the features you use, or as required by law. Please back up anything you need before deleting.",
    ],
  },
  {
    heading: "8. Cookies and Tracking",
    paragraphs: [
      "This service shows no ads and contains no third-party analytics scripts or trackers. We only use the mechanisms required for login sessions (such as a local session token) to keep you signed in.",
    ],
  },
  {
    heading: "9. Your Rights",
    list: [
      "Access: view your accounts, settings and operation history in the console;",
      "Correction: update mailbox configuration, notification channels and account information at any time;",
      "Export: export all data through the instance backup feature;",
      "Deletion: delete accounts, records or the entire instance data.",
    ],
  },
  {
    heading: "10. Policy Updates",
    paragraphs: [
      "This policy may be updated as the service evolves. Updates are reflected in the effective date at the top of this page. If we change how we use Google user data, we will notify you through this page and, for material changes, through an in-product announcement.",
    ],
  },
  {
    heading: "11. Contact Us",
    paragraphs: ["If you have any questions about this policy or your data, contact us at:"],
  },
];

export const PRIVACY_ZH_SECTIONS: LegalSection[] = [
  {
    heading: "1. 我们收集的信息",
    list: [
      "账号信息：您主动添加的邮箱地址、SMTP/IMAP 服务器配置、第三方平台账号绑定关系，以及您的登录账户信息。",
      "邮件内容：您通过本服务收取、发送或转发的邮件，包括其中的验证码、正文与附件信息。",
      "运行数据：系统设置、分组与标签、轮询与自动化任务配置、操作日志等为提供功能所必需的数据。",
    ],
    paragraphs: ["我们不会在您不知情的情况下收集与上述功能无关的个人信息。"],
  },
  {
    heading: "2. 信息的使用目的",
    paragraphs: ["我们仅将收集的信息用于实现本服务的核心功能，包括但不限于："],
    list: [
      "展示与管理您的邮箱账号与平台绑定关系；",
      "按您的配置收取邮件、读取验证码、发送与转发邮件；",
      "执行您配置的自动化任务与通知（如 Telegram、Webhook、浏览器通知）；",
      "提供备份、导出、导入与恢复功能。",
    ],
  },
  {
    heading: "3. Google 用户数据",
    paragraphs: [
      "当您通过 Google OAuth 连接 Gmail 账号时，您明确授权后，本服务仅出于您请求的邮件功能访问您的 Google 数据：",
    ],
    list: [
      "访问范围：您的 Gmail 邮件（含内容、附件与元数据）以及 Google 账号邮箱地址，使用 https://mail.google.com/ 与 OpenID 范围（openid email）；",
      "使用方式：用于收取与展示邮件、自动读取验证码，并按您配置的规则发送、转发邮件与执行自动化；",
      "禁止用途：我们不会将 Google 用户数据用于定向广告、向数据经纪商出售、信用评估，或提供/改进功能以外的任何目的；也不会用于开发、改进或训练 AI/机器学习模型。",
    ],
  },
  {
    heading: "4. 数据的存储",
    paragraphs: [
      "本服务是自托管软件：所有数据默认存储于您自己部署的服务器上的本地数据库（SQLite）与数据目录中，由您完全掌控。我们（服务开发者）无法访问您的数据，也不存在云端中央数据库。",
    ],
    highlight:
      "提示：如果您为他人部署或托管本服务，您将作为该实例的数据控制者，请确保遵守您所在地区适用的数据保护法律。",
  },
  {
    heading: "5. 数据的共享与披露",
    list: [
      "我们不会向任何第三方出售、出租或共享您的数据。",
      "仅在您主动配置的前提下，数据会用于连接您指定的外部服务：例如向您配置的 SMTP 服务器发送邮件、向您配置的 IMAP 服务器收取邮件、向您配置的 Telegram / Webhook 地址推送通知。",
      "除法律法规另有规定外，我们不会在未经您同意的情况下对外披露您的数据。",
    ],
  },
  {
    heading: "6. 数据安全",
    list: [
      "登录口令与邮箱凭据在存储时进行加密处理；",
      "我们建议您通过 HTTPS、强口令、访问控制与定期备份来保护您自己的服务器；",
      "您可以通过“设置”中的备份功能导出完整实例数据，或删除不再需要的账号与数据。",
    ],
  },
  {
    heading: "7. 数据保留与删除",
    paragraphs: [
      "您可以随时在界面中删除账号、邮件或相关记录，也可导出或重置数据。删除实例的数据目录即可永久删除全部数据。我们仅在提供您所使用的功能所需的时间范围内保留数据，或按法律要求保留。请您在操作前自行备份需要保留的数据。",
    ],
  },
  {
    heading: "8. Cookie 与跟踪技术",
    paragraphs: [
      "本服务不投放广告、不包含第三方分析脚本或跟踪器。仅使用登录会话所需的必要机制（如本地会话令牌）来维持您的登录状态。",
    ],
  },
  {
    heading: "9. 您的权利",
    list: [
      "访问与查看：在控制台中查看您的账号、设置与操作记录；",
      "更正与更新：随时修改邮箱配置、通知渠道与个人账户信息；",
      "导出与迁移：通过实例备份功能导出全部数据；",
      "删除：删除账号、记录或整个实例数据。",
    ],
  },
  {
    heading: "10. 政策更新",
    paragraphs: [
      "本政策可能随服务功能的变化而更新。更新后我们会修改本页顶部的“生效日期”。如果我们改变对 Google 用户数据的使用方式，我们会通过本页面通知您，重大变更会通过页面公告等方式提示您。",
    ],
  },
  {
    heading: "11. 联系我们",
    paragraphs: ["如果您对本政策或数据相关事宜有任何疑问，请通过以下邮箱与我们联系："],
  },
];
