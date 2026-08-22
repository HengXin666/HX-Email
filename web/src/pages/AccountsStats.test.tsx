import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { ToastProvider } from "../components/ui/Toast";
import type { AccountStats } from "../types";
import { AccountsStats } from "./AccountsStats";

const getAccountStats = vi.fn();
const listEmailAccounts = vi.fn();
const patrolStatus = vi.fn();
const patrolStart = vi.fn();
const patrolPause = vi.fn();
const patrolResume = vi.fn();
const patrolStop = vi.fn();
const subscribePatrol = vi.fn();

vi.mock("../api/client", () => ({
  api: {
    getAccountStats: (...args: unknown[]) => getAccountStats(...args),
    listEmailAccounts: (...args: unknown[]) => listEmailAccounts(...args),
    patrolStatus: (...args: unknown[]) => patrolStatus(...args),
    patrolStart: (...args: unknown[]) => patrolStart(...args),
    patrolPause: (...args: unknown[]) => patrolPause(...args),
    patrolResume: (...args: unknown[]) => patrolResume(...args),
    patrolStop: (...args: unknown[]) => patrolStop(...args),
  },
  subscribePatrol: (...args: unknown[]) => subscribePatrol(...args),
}));

const bucket = (label: string, min: number, max: number | null) => ({
  label,
  min,
  max,
  valid: 0,
  invalid: 0,
  unknown: 0,
});

const stats: AccountStats = {
  total: 300,
  oauth: 200,
  microsoft: 150,
  google: 50,
  valid: 120,
  invalid: 30,
  unknown: 150,
  failed_refresh: 5,
  last_refresh: "2026-08-21T10:00:00Z",
  by_provider: [
    { provider: "outlook", count: 150 },
    { provider: "gmail", count: 50 },
  ],
  age_buckets: [
    { ...bucket("<7天", 0, 7), valid: 1, unknown: 2 },
    bucket("7-14天", 7, 14),
    bucket("14-30天", 14, 30),
    bucket("30-60天", 30, 60),
    bucket("60-90天", 60, 90),
    bucket("90-180天", 90, 180),
    bucket("180天+", 180, null),
  ],
  daily_new: Array.from({ length: 30 }, (_, i) => ({
    date: `2026-07-${String(i + 1).padStart(2, "0")}`,
    count: i % 5,
  })),
  daily_refresh: Array.from({ length: 30 }, (_, i) => ({
    date: `2026-07-${String(i + 1).padStart(2, "0")}`,
    success: 3 + i,
    failed: i % 3,
  })),
};

beforeEach(() => {
  getAccountStats.mockResolvedValue(stats);
  listEmailAccounts.mockResolvedValue([
    {
      id: 1,
      provider: "outlook",
      primary_address: "a@outlook.com",
      display_name: "A",
      status: "active",
      usable_emails: [],
    },
    {
      id: 2,
      provider: "gmail",
      primary_address: "b@gmail.com",
      display_name: "B",
      status: "active",
      usable_emails: [],
    },
  ]);
  patrolStatus.mockResolvedValue({
    status: "idle",
    mode: "",
    mode_label: "",
    group_id: null,
    total: 0,
    current: 0,
    success: 0,
    failed: 0,
    email: "",
    started_at: null,
    finished_at: null,
    error: "",
  });
  subscribePatrol.mockResolvedValue(undefined);
});

test("stats page renders full account counts and both line charts", async () => {
  render(
    <ToastProvider>
      <AccountsStats />
    </ToastProvider>,
  );

  expect(await screen.findByText("总账号")).toBeInTheDocument();
  expect(screen.getByText("凭证有效")).toBeInTheDocument();
  expect(screen.getByText("凭证失效")).toBeInTheDocument();
  expect(screen.getByText("每日新增账号（近 30 天）")).toBeInTheDocument();
  expect(screen.getByText("每日刷新成功 / 失败（近 30 天）")).toBeInTheDocument();
  expect(screen.getByText("存活时间分布（按凭证状态分段）")).toBeInTheDocument();
  expect(screen.getByText("按服务商分布")).toBeInTheDocument();
  expect(screen.getByText("outlook")).toBeInTheDocument();
  expect(getAccountStats).toHaveBeenCalled();
});

test("age-based picking queries the list API with day filters", async () => {
  render(
    <ToastProvider>
      <AccountsStats />
    </ToastProvider>,
  );

  await screen.findByText("总账号");
  const inputs = screen.getAllByPlaceholderText(/天/);
  fireEvent.change(inputs[0], { target: { value: "10" } });
  fireEvent.click(screen.getByRole("button", { name: "查询" }));

  await waitFor(() => {
    expect(listEmailAccounts).toHaveBeenCalledWith({ min_age_days: 10, max_age_days: undefined });
  });
  expect(await screen.findByText("2 个")).toBeInTheDocument();
  expect(screen.getByText("复制邮箱")).toBeInTheDocument();
});
