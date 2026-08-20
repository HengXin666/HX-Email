interface PlatformPreset {
  key: string;
  name: string;
  domain: string;
  description: string;
  aliases: readonly string[];
  accentColor: string;
  backgroundColor: string;
}

interface PlatformBrand {
  label: string;
  logoUrl: string | null;
  accentColor: string;
  backgroundColor: string;
  fallbackText: string;
}

const FAVICON_SIZE = 128;
const FALLBACK_ACCENT = "#8b949e";
const FALLBACK_BACKGROUND = "#30363d";

export const PRESET_PLATFORMS: readonly PlatformPreset[] = [
  {
    key: "openai",
    name: "OpenAI",
    domain: "openai.com",
    description: "AI 服务",
    aliases: ["open ai", "chatgpt", "chat gpt"],
    accentColor: "#74aa9c",
    backgroundColor: "#f6fffb",
  },
  {
    key: "github",
    name: "GitHub",
    domain: "github.com",
    description: "代码托管",
    aliases: ["git hub"],
    accentColor: "#f0f6fc",
    backgroundColor: "#0d1117",
  },
  {
    key: "google",
    name: "Google",
    domain: "google.com",
    description: "Google 账号",
    aliases: ["gmail", "gmail.com", "googlemail.com"],
    accentColor: "#4285f4",
    backgroundColor: "#ffffff",
  },
  {
    key: "microsoft",
    name: "Microsoft",
    domain: "microsoft.com",
    description: "Microsoft 账号",
    aliases: ["outlook", "office", "live"],
    accentColor: "#7fba00",
    backgroundColor: "#ffffff",
  },
  {
    key: "stripe",
    name: "Stripe",
    domain: "stripe.com",
    description: "支付服务",
    aliases: [],
    accentColor: "#635bff",
    backgroundColor: "#f7f6ff",
  },
  {
    key: "discord",
    name: "Discord",
    domain: "discord.com",
    description: "社区平台",
    aliases: [],
    accentColor: "#5865f2",
    backgroundColor: "#f4f5ff",
  },
  {
    key: "telegram",
    name: "Telegram",
    domain: "telegram.org",
    description: "消息通讯",
    aliases: [],
    accentColor: "#2aabee",
    backgroundColor: "#f2fbff",
  },
  {
    key: "cloudflare",
    name: "Cloudflare",
    domain: "cloudflare.com",
    description: "基础设施",
    aliases: [],
    accentColor: "#f38020",
    backgroundColor: "#fff7f0",
  },
  {
    key: "chatgpt",
    name: "ChatGPT",
    domain: "chatgpt.com",
    description: "AI 服务",
    aliases: ["chat gpt", "openai chat", "codex"],
    accentColor: "#10a37f",
    backgroundColor: "#f2fffc",
  },
  {
    key: "anthropic",
    name: "Anthropic",
    domain: "anthropic.com",
    description: "AI 服务",
    aliases: ["claude", "claude.ai"],
    accentColor: "#d97757",
    backgroundColor: "#fff6f2",
  },
  {
    key: "deepseek",
    name: "DeepSeek",
    domain: "deepseek.com",
    description: "AI 服务",
    aliases: ["deep seek"],
    accentColor: "#4d6bfe",
    backgroundColor: "#f1f3ff",
  },
  {
    key: "apple",
    name: "Apple",
    domain: "apple.com",
    description: "Apple 账号",
    aliases: ["icloud", "appleid"],
    accentColor: "#555555",
    backgroundColor: "#ffffff",
  },
  {
    key: "x",
    name: "X",
    domain: "x.com",
    description: "社交平台",
    aliases: ["twitter", "x.ai"],
    accentColor: "#000000",
    backgroundColor: "#ffffff",
  },
  {
    key: "reddit",
    name: "Reddit",
    domain: "reddit.com",
    description: "社区平台",
    aliases: [],
    accentColor: "#ff4500",
    backgroundColor: "#fff4f0",
  },
  {
    key: "steam",
    name: "Steam",
    domain: "steampowered.com",
    description: "游戏平台",
    aliases: ["steamcommunity"],
    accentColor: "#1b2838",
    backgroundColor: "#e8f0f8",
  },
  {
    key: "whatsapp",
    name: "WhatsApp",
    domain: "whatsapp.com",
    description: "消息通讯",
    aliases: [],
    accentColor: "#25d366",
    backgroundColor: "#f2fff6",
  },
  {
    key: "patreon",
    name: "Patreon",
    domain: "patreon.com",
    description: "内容订阅",
    aliases: ["creator.patreon"],
    accentColor: "#ff424d",
    backgroundColor: "#fff3f4",
  },
  {
    key: "netflix",
    name: "Netflix",
    domain: "netflix.com",
    description: "影音订阅",
    aliases: [],
    accentColor: "#e50914",
    backgroundColor: "#fff3f4",
  },
  {
    key: "gitguardian",
    name: "GitGuardian",
    domain: "gitguardian.com",
    description: "代码安全",
    aliases: [],
    accentColor: "#7f3fee",
    backgroundColor: "#f6f1ff",
  },
  {
    key: "gitkraken",
    name: "GitKraken",
    domain: "gitkraken.com",
    description: "代码工具",
    aliases: [],
    accentColor: "#179287",
    backgroundColor: "#effaf8",
  },
  {
    key: "codeforces",
    name: "Codeforces",
    domain: "codeforces.com",
    description: "竞赛平台",
    aliases: [],
    accentColor: "#1f8acb",
    backgroundColor: "#f0f8ff",
  },
  {
    key: "myfans",
    name: "MyFans",
    domain: "myfans.jp",
    description: "内容订阅",
    aliases: ["myfans"],
    accentColor: "#e6484f",
    backgroundColor: "#fff2f2",
  },
  {
    key: "coursera",
    name: "Coursera",
    domain: "coursera.org",
    description: "在线教育",
    aliases: [],
    accentColor: "#0056d2",
    backgroundColor: "#f0f5ff",
  },
  {
    key: "kraken",
    name: "Kraken",
    domain: "kraken.com",
    description: "加密货币",
    aliases: [],
    accentColor: "#5841d8",
    backgroundColor: "#f4f2ff",
  },
  {
    key: "racknerd",
    name: "RackNerd",
    domain: "racknerd.com",
    description: "云服务器",
    aliases: [],
    accentColor: "#f7941d",
    backgroundColor: "#fff6ec",
  },
  {
    key: "vercel",
    name: "Vercel",
    domain: "vercel.com",
    description: "部署平台",
    aliases: [],
    accentColor: "#111111",
    backgroundColor: "#ffffff",
  },
  {
    key: "oracle-cloud",
    name: "Oracle Cloud",
    domain: "oraclecloud.com",
    description: "云服务器",
    aliases: ["oracle"],
    accentColor: "#f80000",
    backgroundColor: "#fff3f3",
  },
];

export function getPlatformBrand(name: string): PlatformBrand {
  const trimmedName = name.trim();
  const preset = findPlatformPreset(trimmedName);
  const senderDomain = extractDomain(trimmedName);

  if (preset) {
    return {
      label: preset.name,
      logoUrl: getLogoUrl(preset.domain),
      accentColor: preset.accentColor,
      backgroundColor: preset.backgroundColor,
      fallbackText: getFallbackText(preset.name),
    };
  }

  if (senderDomain) {
    return {
      label: senderDomain,
      logoUrl: getLogoUrl(senderDomain),
      accentColor: FALLBACK_ACCENT,
      backgroundColor: FALLBACK_BACKGROUND,
      fallbackText: getFallbackText(senderDomain),
    };
  }

  return {
    label: trimmedName || "Platform",
    logoUrl: null,
    accentColor: FALLBACK_ACCENT,
    backgroundColor: FALLBACK_BACKGROUND,
    fallbackText: getFallbackText(trimmedName),
  };
}

function findPlatformPreset(name: string): PlatformPreset | null {
  const normalizedName = normalizePlatformName(name);
  if (!normalizedName) return null;
  const senderDomain = extractDomain(name);

  return (
    PRESET_PLATFORMS.find((preset: PlatformPreset) => {
      const names = [preset.key, preset.name, preset.domain, ...preset.aliases];
      const hasExactName = names.some(
        (candidate: string) => normalizePlatformName(candidate) === normalizedName,
      );
      if (hasExactName || !senderDomain) return hasExactName;
      const knownDomains = [preset.domain, ...preset.aliases.filter(isDomain)];
      return knownDomains.some(
        (domain: string) => senderDomain === domain || senderDomain.endsWith(`.${domain}`),
      );
    }) ?? null
  );
}

function extractDomain(value: string): string | null {
  const emailDomain = value.match(/@([a-z0-9.-]+\.[a-z]{2,})/i)?.[1];
  if (emailDomain) return emailDomain.toLowerCase();
  const plainValue = value
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, "")
    .split("/")[0];
  return isDomain(plainValue) ? plainValue : null;
}

function isDomain(value: string): boolean {
  return /^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}$/i.test(value);
}

function normalizePlatformName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[\s._-]+/g, "");
}

function getLogoUrl(domain: string): string {
  return `https://www.google.com/s2/favicons?domain=${domain}&sz=${FAVICON_SIZE}`;
}

function getFallbackText(name: string): string {
  const parts = name
    .trim()
    .split(/[\s._-]+/)
    .filter((part: string) => part.length > 0);

  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return parts
    .slice(0, 2)
    .map((part: string) => part[0])
    .join("")
    .toUpperCase();
}
