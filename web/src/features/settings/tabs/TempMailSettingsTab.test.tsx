import { fireEvent, render, screen } from "@testing-library/react";
import type React from "react";
import { useState } from "react";
import { expect, test, vi } from "vitest";
import type { TempMailUpstream } from "../impl/temp_mail_upstreams";
import { TempMailSettingsTab } from "./TempMailSettingsTab";

const mocks = vi.hoisted(() => ({
  syncCFDomains: vi.fn(),
}));

vi.mock("../../../api/client", () => ({
  api: {
    syncCFDomains: mocks.syncCFDomains,
  },
}));

interface RenderOptions {
  domains?: string[];
  excluded?: string[];
  defaultDomain?: string;
  upstreams?: Partial<TempMailUpstream>[];
}

function upstream(patch: Partial<TempMailUpstream>): TempMailUpstream {
  return {
    id: "u1",
    name: "",
    base_url: "https://worker.example.workers.dev",
    admin_key: "key",
    custom_auth: "",
    enabled: true,
    domains: [],
    excluded_domains: [],
    ...patch,
  };
}

/**
 * 复刻父组件 Settings.tsx 的行为: setSetting 只改本地 state, 由「保存设置」统一 PUT。
 * 不传 upstreams 时用旧的单上游键, 顺带覆盖「旧配置自动读成一个上游」的迁移路径。
 */
function renderTab(options: RenderOptions = {}) {
  const setSetting = vi.fn();
  const initialSettings: Record<string, string> = options.upstreams
    ? { cf_worker_upstreams: JSON.stringify(options.upstreams.map(upstream)) }
    : {
        cf_worker_base_url: "https://worker.example.workers.dev",
        cf_worker_domains: JSON.stringify(options.domains ?? ["a.com", "b.com", "c.com"]),
        cf_worker_excluded_domains: JSON.stringify(options.excluded ?? []),
      };
  initialSettings.cf_worker_default_domain = options.defaultDomain ?? "";

  const Harness: React.FC = () => {
    const [settings, setSettings] = useState<Record<string, string>>(initialSettings);
    const updateSetting = (key: string, value: string): void => {
      setSetting(key, value);
      setSettings((current) => ({ ...current, [key]: value }));
    };
    return (
      <TempMailSettingsTab
        settings={settings}
        setSetting={updateSetting}
        toast={vi.fn()}
        user={null}
        accounts={[]}
      />
    );
  };

  render(<Harness />);
  /** 最近一次写出的上游列表。 */
  const lastUpstreams = (): TempMailUpstream[] => {
    const calls = setSetting.mock.calls.filter(([key]) => key === "cf_worker_upstreams");
    return JSON.parse(String(calls.at(-1)?.[1] ?? "[]"));
  };
  return { setSetting, lastUpstreams };
}

test("旧单上游配置读成一个上游; 删除域名写入它的排除列表并回退默认域名", () => {
  const { setSetting, lastUpstreams } = renderTab({ defaultDomain: "a.com" });

  expect(screen.getByRole("combobox", { name: "默认域名" })).toHaveTextContent("a.com");

  fireEvent.click(screen.getByRole("button", { name: "删除域名 a.com" }));

  const [only] = lastUpstreams();
  expect(only.id).toBe("default");
  expect(only.base_url).toBe("https://worker.example.workers.dev");
  expect(only.excluded_domains).toEqual(["a.com"]);
  expect(setSetting).toHaveBeenCalledWith("cf_worker_default_domain", "b.com");
  expect(screen.queryByRole("button", { name: "删除域名 a.com" })).toBeNull();
  expect(screen.getByRole("combobox", { name: "默认域名" })).toHaveTextContent("b.com");
  expect(screen.getByText("已删除的域名 (1)")).toBeInTheDocument();
});

test("恢复域名 (大小写不同也算同一个) 后回到可用列表", () => {
  const { lastUpstreams } = renderTab({ excluded: ["@B.COM"] });

  expect(screen.queryByRole("button", { name: "删除域名 b.com" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "恢复域名 b.com" }));

  expect(lastUpstreams()[0].excluded_domains).toEqual([]);
  expect(screen.getByRole("button", { name: "删除域名 b.com" })).toBeInTheDocument();
  expect(screen.queryByText(/已删除的域名/)).toBeNull();
});

test("全部删除时给出警告, 且不渲染空的默认域名下拉", () => {
  const { setSetting } = renderTab({ domains: ["a.com"], defaultDomain: "a.com" });

  fireEvent.click(screen.getByRole("button", { name: "删除域名 a.com" }));

  expect(setSetting).toHaveBeenCalledWith("cf_worker_default_domain", "");
  expect(screen.getByText(/所有域名都已被删除/)).toBeInTheDocument();
  expect(screen.queryByRole("combobox", { name: "默认域名" })).toBeNull();
});

test("默认域名下拉是所有启用上游的并集, 停用的上游不参与", () => {
  renderTab({
    upstreams: [
      { id: "a", name: "A", domains: ["a.com"] },
      { id: "b", name: "B", domains: ["b.com"] },
      { id: "c", name: "C", domains: ["c.com"], enabled: false },
    ],
    defaultDomain: "b.com",
  });

  const select = screen.getByRole("combobox", { name: "默认域名" });
  expect(select).toHaveTextContent("b.com · B");
  expect(screen.getAllByRole("button", { name: /^删除域名/ })).toHaveLength(3);
});

test("添加、移动、删除上游都写回 cf_worker_upstreams", () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  const { lastUpstreams } = renderTab({
    upstreams: [{ id: "a", name: "A", domains: ["a.com"] }],
  });

  fireEvent.click(screen.getByRole("button", { name: /添加上游/ }));
  const added = lastUpstreams();
  expect(added).toHaveLength(2);
  expect(added[1].id).toMatch(/^u_/);
  expect(screen.getByText(/已启用的上游必须填写/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "上移上游 上游 2" }));
  expect(lastUpstreams().map((item) => item.id)).toEqual([added[1].id, "a"]);

  fireEvent.click(screen.getByRole("button", { name: "删除上游 A" }));
  expect(lastUpstreams().map((item) => item.id)).toEqual([added[1].id]);
  confirm.mockRestore();
});

test("同步只更新该上游, 用响应的 excluded_domains 剪枝, 并跳过被排除的默认域名", async () => {
  mocks.syncCFDomains.mockResolvedValue({
    success: true,
    domains: ["b1.com", "b2.com"],
    excluded_domains: ["b2.com"],
    default_domain: "b2.com",
    message: "已同步 2 个域名",
  });
  const { setSetting, lastUpstreams } = renderTab({
    upstreams: [
      { id: "a", name: "A", domains: ["a.com"], excluded_domains: ["a.com"] },
      {
        id: "b",
        name: "B",
        base_url: "https://b.dev",
        custom_auth: "pw",
        domains: ["old.com"],
        excluded_domains: ["old.com"],
      },
    ],
  });

  fireEvent.click(screen.getAllByRole("button", { name: /同步并测试/ })[1]);

  await vi.waitFor(() => {
    expect(lastUpstreams()[1].domains).toEqual(["b1.com", "b2.com"]);
  });
  expect(mocks.syncCFDomains).toHaveBeenCalledWith({
    upstream_id: "b",
    worker_url: "https://b.dev",
    custom_auth: "pw",
  });
  expect(lastUpstreams()[1].excluded_domains).toEqual(["b2.com"]);
  expect(lastUpstreams()[0].domains).toEqual(["a.com"]);
  // Worker 给的默认域名 b2.com 已被排除 -> 回退到并集里的第一个 b1.com
  expect(setSetting).toHaveBeenCalledWith("cf_worker_default_domain", "b1.com");
});

test("同步响应缺少 excluded_domains 时按旧排除列表与新域名求交", async () => {
  mocks.syncCFDomains.mockResolvedValue({
    success: true,
    domains: ["a.com", "c.com"],
    default_domain: "a.com",
    message: "已同步 2 个域名",
  });
  const { lastUpstreams } = renderTab({ domains: ["a.com", "b.com"], excluded: ["b.com"] });

  fireEvent.click(screen.getByRole("button", { name: /同步并测试/ }));

  await vi.waitFor(() => {
    expect(lastUpstreams()[0].domains).toEqual(["a.com", "c.com"]);
  });
  expect(lastUpstreams()[0].excluded_domains).toEqual([]);
});
