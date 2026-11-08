import { expect, test } from "vitest";
import {
  moveUpstream,
  parseUpstreams,
  resolveGlobalDefault,
  type TempMailUpstream,
  usableDomainOptions,
} from "./temp_mail_upstreams";

function upstream(id: string, domains: string[], patch: Partial<TempMailUpstream> = {}) {
  return {
    id,
    name: id.toUpperCase(),
    base_url: `https://${id}.dev`,
    admin_key: "k",
    custom_auth: "",
    enabled: true,
    domains,
    excluded_domains: [],
    ...patch,
  };
}

test("新键优先; 为空时旧单上游键读成 default", () => {
  const stored = JSON.stringify([upstream("a", ["a.com"])]);
  expect(parseUpstreams({ cf_worker_upstreams: stored }).map((item) => item.id)).toEqual(["a"]);

  const legacy = parseUpstreams({
    cf_worker_upstreams: "[]",
    cf_worker_base_url: "https://legacy.dev",
    cf_worker_domains: '["@x.com"]',
  });
  expect(legacy).toHaveLength(1);
  expect(legacy[0]).toMatchObject({ id: "default", base_url: "https://legacy.dev" });
  expect(legacy[0].domains).toEqual(["@x.com"]);

  expect(parseUpstreams({})).toEqual([]);
  expect(parseUpstreams({ cf_worker_upstreams: "not json" })).toEqual([]);
});

test("并集按上游顺序去重, 跳过停用上游与各自的排除域名", () => {
  const list = [
    upstream("a", ["@a.com", "@shared.com"], { excluded_domains: ["shared.com"] }),
    upstream("b", ["@B.com", "@Shared.com"]),
    upstream("c", ["@c.com"], { enabled: false }),
  ];

  expect(usableDomainOptions(list).map((item) => [item.domain, item.upstreamId])).toEqual([
    ["@a.com", "a"],
    ["@B.com", "b"],
    ["@Shared.com", "b"],
  ]);
});

test("全局默认域名: 可用则保留, 否则用 fallback, 再否则第一个; 从未同步时原样保留", () => {
  const list = [upstream("a", ["a.com", "b.com"], { excluded_domains: ["b.com"] })];

  expect(resolveGlobalDefault(list, "a.com")).toBe("a.com");
  expect(resolveGlobalDefault(list, "b.com", "a.com")).toBe("a.com");
  expect(resolveGlobalDefault(list, "gone.com")).toBe("a.com");
  expect(resolveGlobalDefault([upstream("a", [])], "kept.com")).toBe("kept.com");
});

test("移动越界时保持原顺序", () => {
  const list = [upstream("a", []), upstream("b", [])];

  expect(moveUpstream(list, "a", -1).map((item) => item.id)).toEqual(["a", "b"]);
  expect(moveUpstream(list, "a", 1).map((item) => item.id)).toEqual(["b", "a"]);
});
