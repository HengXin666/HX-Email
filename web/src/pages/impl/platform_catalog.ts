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
