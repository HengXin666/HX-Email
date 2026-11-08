/**
 * 临时邮箱「可用域名」的纯函数层: 解析同步结果、按排除列表切分、以及删除/恢复/同步后
 * 应该写回的排除列表。
 *
 * 每个上游的 `excluded_domains` 与它的 `domains` 正交: 前者是用户的减法。域名比较
 * 忽略前导 `@` 与大小写, 因为 CF Worker 的 `open_api/settings` 返回的是 `@example.com` 形式。
 */

interface DomainSplit {
  /** 仍参与轮换的域名, 顺序与同步结果一致。 */
  available: string[];
  /** 用户删除的域名, 顺序与同步结果一致; 不在同步结果里的幽灵项会被丢弃。 */
  excluded: string[];
}

/** 域名比较用的归一化: 去掉首尾空白与前导 `@` 并转小写 (与后端 normalize_domain 一致)。 */
function normalizeDomain(domain: string): string {
  return domain.trim().replace(/^@+/, "").trim().toLowerCase();
}

/** 把设置里的 JSON 字符串数组解析成域名列表; 非法 JSON 或非字符串项一律丢弃。 */
export function parseDomainList(value: string | undefined): string[] {
  try {
    const parsed: unknown = JSON.parse(value || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (domain): domain is string => typeof domain === "string" && domain.length > 0,
    );
  } catch {
    return [];
  }
}

/** 该域名是否在排除列表里 (比较时忽略前导 `@`)。 */
export function isDomainExcluded(domain: string, excluded: readonly string[]): boolean {
  const target: string = normalizeDomain(domain);
  return excluded.some((item: string): boolean => normalizeDomain(item) === target);
}

/**
 * 按排除列表把同步来的域名切成「可用」与「已删除」两半。
 * 排除列表是对同步全集的本地减法, 决策见 .agents/notes/implemented/feature/2026-10-19-temp-mail-excluded-domains.md
 */
export function splitDomainsByExclusion(
  domains: readonly string[],
  excluded: readonly string[],
): DomainSplit {
  const excludedSet: Set<string> = new Set(
    excluded.map((item: string): string => normalizeDomain(item)),
  );
  const available: string[] = [];
  const deleted: string[] = [];
  for (const domain of domains) {
    if (excludedSet.has(normalizeDomain(domain))) deleted.push(domain);
    else available.push(domain);
  }
  return { available, excluded: deleted };
}

/** 删除一个域名后的排除列表: 已排除的域名不会重复出现, 幽灵项被剪掉。 */
export function withDomainExcluded(
  domains: readonly string[],
  excluded: readonly string[],
  domain: string,
): string[] {
  const current: DomainSplit = splitDomainsByExclusion(domains, excluded);
  if (isDomainExcluded(domain, current.excluded)) return current.excluded;
  return [...current.excluded, domain];
}

/** 恢复一个域名后的排除列表: 归一化后相等的项全部移除。 */
export function withDomainRestored(
  domains: readonly string[],
  excluded: readonly string[],
  domain: string,
): string[] {
  const target: string = normalizeDomain(domain);
  return splitDomainsByExclusion(domains, excluded).excluded.filter(
    (item: string): boolean => normalizeDomain(item) !== target,
  );
}

/**
 * 同步成功后应该写回的排除列表: 优先用后端返回的 `excluded_domains`
 * (它已经剪过枝), 字段缺失时退化为「旧排除列表 ∩ 新域名列表」。
 */
export function mergeSyncedExclusions(
  domains: readonly string[],
  excluded: readonly string[],
  reported: readonly string[] | undefined,
): string[] {
  const source: readonly string[] = reported ?? excluded;
  return splitDomainsByExclusion(domains, source).excluded;
}
