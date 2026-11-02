import { fireEvent, render, screen } from "@testing-library/react";
import type React from "react";
import { useState } from "react";
import { expect, test, vi } from "vitest";
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
}

/**
 * 复刻父组件 Settings.tsx 的行为: setSetting 只改本地 state, 由「保存设置」统一 PUT。
 * 测试必须走这条路径, 否则组件永远看不到自己写出去的排除列表。
 */
function renderTab(options: RenderOptions = {}) {
  const setSetting = vi.fn();
  const initialSettings: Record<string, string> = {
    cf_worker_base_url: "https://worker.example.workers.dev",
    cf_worker_domains: JSON.stringify(options.domains ?? ["a.com", "b.com", "c.com"]),
    cf_worker_excluded_domains: JSON.stringify(options.excluded ?? []),
    cf_worker_default_domain: options.defaultDomain ?? "",
  };

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
  return { setSetting };
}

/** 「已删除的域名」区里的恢复按钮 (aria-label 以「恢复域名」开头)。 */
function restoreButtons(): HTMLElement[] {
  return screen.queryAllByRole("button", { name: /^恢复域名/ });
}

test("删除域名写入排除列表, 并从默认域名下拉里消失", () => {
  const { setSetting } = renderTab({ defaultDomain: "a.com" });

  expect(screen.getByRole("combobox", { name: "默认域名" })).toHaveTextContent("a.com");
  expect(restoreButtons()).toHaveLength(0);

  fireEvent.click(screen.getByRole("button", { name: "删除域名 a.com" }));

  expect(setSetting).toHaveBeenCalledWith("cf_worker_excluded_domains", JSON.stringify(["a.com"]));
  // 被删的正是当前默认域名 -> 立刻回退到剩余第一个
  expect(setSetting).toHaveBeenCalledWith("cf_worker_default_domain", "b.com");
  // 默认域名下拉只剩未排除的域名
  expect(screen.queryByRole("button", { name: "删除域名 a.com" })).toBeNull();
  expect(screen.getByRole("combobox", { name: "默认域名" })).toHaveTextContent("b.com");
  expect(screen.getByText("已删除的域名 (1)")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "恢复域名 a.com" })).toBeInTheDocument();
});

test("恢复域名后回到可用列表并写出空排除列表", () => {
  const { setSetting } = renderTab({ excluded: ["b.com"] });

  expect(screen.getByText("已删除的域名 (1)")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "删除域名 b.com" })).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "恢复域名 b.com" }));

  expect(setSetting).toHaveBeenCalledWith("cf_worker_excluded_domains", JSON.stringify([]));
  expect(screen.getByRole("button", { name: "删除域名 b.com" })).toBeInTheDocument();
  expect(screen.queryByText(/已删除的域名/)).toBeNull();
});

test("全部删除时给出创建会被拒绝的警告, 且不渲染空的默认域名下拉", () => {
  const { setSetting } = renderTab({ domains: ["a.com"], defaultDomain: "a.com" });

  fireEvent.click(screen.getByRole("button", { name: "删除域名 a.com" }));

  expect(setSetting).toHaveBeenCalledWith("cf_worker_excluded_domains", JSON.stringify(["a.com"]));
  expect(setSetting).toHaveBeenCalledWith("cf_worker_default_domain", "");
  expect(screen.getByText(/所有域名都已被删除/)).toBeInTheDocument();
  expect(screen.queryByRole("combobox", { name: "默认域名" })).toBeNull();
});

test("同步成功后用响应的 excluded_domains 剪枝, 并跳过被排除的默认域名", async () => {
  mocks.syncCFDomains.mockResolvedValue({
    success: true,
    domains: ["a.com", "b.com"],
    excluded_domains: ["b.com"],
    default_domain: "b.com",
    message: "已同步 2 个域名",
  });
  const { setSetting } = renderTab({
    domains: ["a.com", "b.com", "old.com"],
    excluded: ["old.com"],
  });

  fireEvent.click(screen.getByRole("button", { name: /同步并测试/ }));

  await vi.waitFor(() => {
    expect(setSetting).toHaveBeenCalledWith(
      "cf_worker_domains",
      JSON.stringify(["a.com", "b.com"]),
    );
  });
  expect(setSetting).toHaveBeenCalledWith("cf_worker_excluded_domains", JSON.stringify(["b.com"]));
  // 后端给的默认域名 b.com 已被排除 -> 回退到 a.com
  expect(setSetting).toHaveBeenCalledWith("cf_worker_default_domain", "a.com");
});

test("同步响应缺少 excluded_domains 时按旧排除列表与新域名求交", async () => {
  mocks.syncCFDomains.mockResolvedValue({
    success: true,
    domains: ["a.com", "c.com"],
    default_domain: "a.com",
    message: "已同步 2 个域名",
  });
  const { setSetting } = renderTab({ domains: ["a.com", "b.com"], excluded: ["b.com"] });

  fireEvent.click(screen.getByRole("button", { name: /同步并测试/ }));

  await vi.waitFor(() => {
    expect(setSetting).toHaveBeenCalledWith(
      "cf_worker_domains",
      JSON.stringify(["a.com", "c.com"]),
    );
  });
  // b.com 已不在新域名列表里 -> 幽灵项被剪掉
  expect(setSetting).toHaveBeenCalledWith("cf_worker_excluded_domains", JSON.stringify([]));
});
