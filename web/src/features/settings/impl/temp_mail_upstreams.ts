/**
 * 临时邮箱「多个 CF Worker 上游」的纯函数层: 解析/序列化 `cf_worker_upstreams`、增删改排、
 * 以及所有启用上游可用域名的并集。
 *
 * 新键为空时把旧的单上游键 (`cf_worker_base_url` 等) 读成 id 为 `default` 的一项, 与后端
 * `upstreams_from_values` 一致; 一旦保存过 `cf_worker_upstreams`, 后端会清空旧键。
 */

import { isDomainExcluded, parseDomainList, splitDomainsByExclusion } from "./temp_mail_domains";

export interface TempMailUpstream {
  id: string;
  name: string;
  base_url: string;
  admin_key: string;
  custom_auth: string;
  enabled: boolean;
  /** 从该 Worker 同步来的域名全集。 */
  domains: string[];
  /** 该上游上被用户删除 (不参与轮换) 的域名。 */
  excluded_domains: string[];
}

export interface DomainOption {
  domain: string;
  upstreamId: string;
  upstreamLabel: string;
}

const LEGACY_UPSTREAM_ID = "default";

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.length > 0)
    : [];
}

function fromUnknown(value: unknown): TempMailUpstream | null {
  if (typeof value !== "object" || value === null) return null;
  const item = value as Record<string, unknown>;
  const id: string = asString(item.id);
  if (!id) return null;
  return {
    id,
    name: asString(item.name),
    base_url: asString(item.base_url),
    admin_key: asString(item.admin_key),
    custom_auth: asString(item.custom_auth),
    enabled: item.enabled !== false,
    domains: asStringList(item.domains),
    excluded_domains: asStringList(item.excluded_domains),
  };
}

function parseStored(value: string | undefined): TempMailUpstream[] {
  try {
    const parsed: unknown = JSON.parse(value || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.map(fromUnknown).filter((item): item is TempMailUpstream => item !== null);
  } catch {
    return [];
  }
}

function legacyUpstream(settings: Record<string, string>): TempMailUpstream | null {
  const baseUrl: string = settings.cf_worker_base_url || "";
  const adminKey: string = settings.cf_worker_admin_key || "";
  const customAuth: string = settings.cf_worker_custom_auth || "";
  const domains: string[] = parseDomainList(settings.cf_worker_domains);
  const excluded: string[] = parseDomainList(settings.cf_worker_excluded_domains);
  if (!baseUrl && !adminKey && !customAuth && !domains.length && !excluded.length) return null;
  return {
    id: LEGACY_UPSTREAM_ID,
    name: "",
    base_url: baseUrl,
    admin_key: adminKey,
    custom_auth: customAuth,
    enabled: true,
    domains,
    excluded_domains: excluded,
  };
}

/**
 * 设置里的上游列表; 新键为空时回退到旧单上游键。
 * .agents/notes/implemented/feature/2026-11-08-temp-mail-multi-upstream.md
 */
export function parseUpstreams(settings: Record<string, string>): TempMailUpstream[] {
  const stored: TempMailUpstream[] = parseStored(settings.cf_worker_upstreams);
  if (stored.length) return stored;
  const legacy: TempMailUpstream | null = legacyUpstream(settings);
  return legacy ? [legacy] : [];
}

export function serializeUpstreams(upstreams: readonly TempMailUpstream[]): string {
  return JSON.stringify(upstreams);
}

export function createUpstream(existing: readonly TempMailUpstream[]): TempMailUpstream {
  const taken: Set<string> = new Set(existing.map((item) => item.id));
  let id: string = "";
  do {
    id = `u_${Math.random().toString(36).slice(2, 8)}`;
  } while (taken.has(id));
  return {
    id,
    name: "",
    base_url: "",
    admin_key: "",
    custom_auth: "",
    enabled: true,
    domains: [],
    excluded_domains: [],
  };
}

export function patchUpstream(
  upstreams: readonly TempMailUpstream[],
  id: string,
  patch: Partial<Omit<TempMailUpstream, "id">>,
): TempMailUpstream[] {
  return upstreams.map((item) => (item.id === id ? { ...item, ...patch } : item));
}

export function removeUpstream(
  upstreams: readonly TempMailUpstream[],
  id: string,
): TempMailUpstream[] {
  return upstreams.filter((item) => item.id !== id);
}

export function moveUpstream(
  upstreams: readonly TempMailUpstream[],
  id: string,
  offset: -1 | 1,
): TempMailUpstream[] {
  const index: number = upstreams.findIndex((item) => item.id === id);
  const target: number = index + offset;
  if (index < 0 || target < 0 || target >= upstreams.length) return [...upstreams];
  const next: TempMailUpstream[] = [...upstreams];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

export function upstreamLabel(upstream: TempMailUpstream, index: number): string {
  return upstream.name || upstream.base_url || `上游 ${index + 1}`;
}

/** 所有启用上游的可用域名并集; 同一域名多个上游都提供时, 排在前面的上游胜出。 */
export function usableDomainOptions(upstreams: readonly TempMailUpstream[]): DomainOption[] {
  const options: DomainOption[] = [];
  upstreams.forEach((upstream, index) => {
    if (!upstream.enabled) return;
    const { available } = splitDomainsByExclusion(upstream.domains, upstream.excluded_domains);
    for (const domain of available) {
      const seen: string[] = options.map((option) => option.domain);
      if (isDomainExcluded(domain, seen)) continue;
      options.push({
        domain,
        upstreamId: upstream.id,
        upstreamLabel: upstreamLabel(upstream, index),
      });
    }
  });
  return options;
}

/**
 * 上游变化后的全局默认域名: 首选值仍可用就保留, 否则依次回退到 `fallback` (例如刚同步的
 * Worker 默认域名) 与并集里的第一个; 一个都没有时返回空字符串。
 */
export function resolveGlobalDefault(
  upstreams: readonly TempMailUpstream[],
  preferred: string,
  fallback = "",
): string {
  const usable: string[] = usableDomainOptions(upstreams).map((option) => option.domain);
  // 从未同步过任何域名时保留用户填的默认值 (与后端 resolve_cf_domains 一致)
  if (!upstreams.some((upstream) => upstream.domains.length)) return preferred;
  if (preferred && isDomainExcluded(preferred, usable)) return preferred;
  if (fallback && isDomainExcluded(fallback, usable)) return fallback;
  return usable[0] ?? "";
}
