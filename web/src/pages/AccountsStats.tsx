import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import {
  IconAlertTriangle,
  IconCheck,
  IconClock,
  IconCopy,
  IconDatabase,
  IconKey,
  IconMail,
  IconRefresh,
  IconSearch,
  IconShield,
  IconX,
} from "../components/icons";
import { Topbar } from "../components/layout";
import { Card } from "../components/ui/Primitives";
import { useToast } from "../components/ui/Toast";
import type { AccountStats, EmailAccount } from "../types";
import { copyToClipboard } from "../utils/clipboard";
import { accountCredentialState } from "../utils/credential";
import { formatRelativeTime } from "../utils/time";
import { PatrolPanel } from "./impl/PatrolPanel";
import { type ChartSeries, StatChart } from "./impl/StatChart";

const StatCard: React.FC<{
  label: string;
  value: number;
  tone?: "neutral" | "success" | "danger" | "muted";
  icon: React.ReactNode;
}> = ({ label, value, tone = "neutral", icon }) => {
  const valueClass =
    tone === "success"
      ? "text-gh-success"
      : tone === "danger"
        ? "text-gh-danger"
        : tone === "muted"
          ? "text-gh-text-muted"
          : "text-gh-text";
  return (
    <Card className="p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] text-gh-text-secondary">{label}</span>
        {icon}
      </div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${valueClass}`}>{value}</div>
    </Card>
  );
};

export const AccountsStats: React.FC = () => {
  const { toast } = useToast();
  const [stats, setStats] = useState<AccountStats | null>(null);
  const [loading, setLoading] = useState(true);
  // 按存活天数取号
  const [minDays, setMinDays] = useState("");
  const [maxDays, setMaxDays] = useState("");
  const [picked, setPicked] = useState<EmailAccount[] | null>(null);
  const [picking, setPicking] = useState(false);

  const loadStats = useCallback(async (): Promise<void> => {
    try {
      setStats(await api.getAccountStats());
    } catch (err: any) {
      toast(err.message, "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  const dailyNewSeries: ChartSeries[] = useMemo(() => {
    if (!stats) return [];
    return [
      {
        key: "new",
        label: "每日新增账号",
        color: "#58a6ff",
        fill: true,
        points: stats.daily_new.map((d) => ({ label: d.date.slice(5), value: d.count })),
      },
    ];
  }, [stats]);

  const dailyRefreshSeries: ChartSeries[] = useMemo(() => {
    if (!stats) return [];
    return [
      {
        key: "success",
        label: "刷新成功",
        color: "#3fb950",
        points: stats.daily_refresh.map((d) => ({ label: d.date.slice(5), value: d.success })),
      },
      {
        key: "failed",
        label: "刷新失败",
        color: "#f85149",
        points: stats.daily_refresh.map((d) => ({ label: d.date.slice(5), value: d.failed })),
      },
    ];
  }, [stats]);

  const handlePick = useCallback(async (): Promise<void> => {
    const min = minDays.trim() ? Number(minDays.trim()) : undefined;
    const max = maxDays.trim() ? Number(maxDays.trim()) : undefined;
    if (min !== undefined && (Number.isNaN(min) || min < 0)) {
      toast("最小天数必须是 ≥0 的整数", "error");
      return;
    }
    if (max !== undefined && (Number.isNaN(max) || max < 0)) {
      toast("最大天数必须是 ≥0 的整数", "error");
      return;
    }
    if (min !== undefined && max !== undefined && min > max) {
      toast("最小天数不能大于最大天数", "error");
      return;
    }
    setPicking(true);
    try {
      setPicked(await api.listEmailAccounts({ min_age_days: min, max_age_days: max }));
    } catch (err: any) {
      toast(err.message, "error");
      setPicked(null);
    } finally {
      setPicking(false);
    }
  }, [minDays, maxDays, toast]);

  const copyPicked = async (): Promise<void> => {
    if (!picked || picked.length === 0) return;
    const copied = await copyToClipboard(picked.map((a) => a.primary_address).join("\n"));
    toast(
      copied ? `已复制 ${picked.length} 个邮箱地址` : "复制失败，请手动复制",
      copied ? "success" : "error",
    );
  };

  const maxBucketTotal = Math.max(
    1,
    ...(stats?.age_buckets.map((b) => b.valid + b.invalid + b.unknown) ?? [1]),
  );
  const pickedValid = picked?.filter((a) => accountCredentialState(a) === "valid").length ?? 0;
  const pickedInvalid = picked?.filter((a) => accountCredentialState(a) === "invalid").length ?? 0;
  const maxProviderCount = Math.max(1, ...(stats?.by_provider.map((p) => p.count) ?? [1]));

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
      <Topbar
        title="账号统计"
        subtitle="凭证状态、存活时间、每日新增与刷新趋势、按天数取号与巡检"
        actions={
          <button
            onClick={() => void loadStats()}
            className="p-1.5 rounded-md text-gh-text-muted hover:text-gh-text hover:bg-gh-border/40 transition-colors"
            title="刷新统计"
          >
            <IconRefresh size={15} className={loading ? "animate-spin" : ""} />
          </button>
        }
      />
      <div className="flex-1 overflow-auto">
        <div className="max-w-6xl mx-auto p-6 space-y-5">
          {!stats ? (
            <div className="py-16 text-center text-sm text-gh-text-secondary">加载中...</div>
          ) : (
            <>
              {/* 统计卡片 */}
              <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
                <StatCard label="总账号" value={stats.total} icon={<IconMail size={14} />} />
                <StatCard label="OAuth 账号" value={stats.oauth} icon={<IconShield size={14} />} />
                <StatCard label="Microsoft" value={stats.microsoft} icon={<IconKey size={14} />} />
                <StatCard label="Google" value={stats.google} icon={<IconKey size={14} />} />
                <StatCard
                  label="凭证有效"
                  value={stats.valid}
                  tone="success"
                  icon={<IconCheck size={14} />}
                />
                <StatCard
                  label="凭证失效"
                  value={stats.invalid}
                  tone="danger"
                  icon={<IconAlertTriangle size={14} />}
                />
                <StatCard
                  label="未验证"
                  value={stats.unknown}
                  tone="muted"
                  icon={<IconX size={14} />}
                />
                <StatCard
                  label="刷新失败"
                  value={stats.failed_refresh}
                  tone={stats.failed_refresh > 0 ? "danger" : "neutral"}
                  icon={<IconAlertTriangle size={14} />}
                />
              </div>

              {/* 折线图 */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <Card className="p-4">
                  <h3 className="text-sm font-semibold text-gh-text mb-3">
                    每日新增账号（近 30 天）
                  </h3>
                  <StatChart series={dailyNewSeries} />
                </Card>
                <Card className="p-4">
                  <h3 className="text-sm font-semibold text-gh-text mb-3">
                    每日刷新成功 / 失败（近 30 天）
                  </h3>
                  <StatChart series={dailyRefreshSeries} />
                </Card>
              </div>

              {/* 存活分布 + 服务商 */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <Card className="p-4">
                  <h3 className="text-sm font-semibold text-gh-text mb-1">
                    存活时间分布（按凭证状态分段）
                  </h3>
                  <div className="text-[11px] text-gh-text-muted mb-3">
                    <span className="inline-flex items-center gap-1 mr-3">
                      <span className="w-2 h-2 rounded-sm bg-gh-success" />
                      有效
                    </span>
                    <span className="inline-flex items-center gap-1 mr-3">
                      <span className="w-2 h-2 rounded-sm bg-gh-danger" />
                      失效
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <span className="w-2 h-2 rounded-sm bg-gh-text-muted/40" />
                      未验证
                    </span>
                  </div>
                  <div className="space-y-2.5">
                    {stats.age_buckets.map((bucket) => {
                      const bucketTotal = bucket.valid + bucket.invalid + bucket.unknown;
                      return (
                        <div key={bucket.label}>
                          <div className="flex items-center justify-between text-[11px] mb-1">
                            <span className="text-gh-text-secondary">{bucket.label}</span>
                            <span className="text-gh-text-muted tabular-nums">
                              有效 {bucket.valid} · 失效 {bucket.invalid} · 未验证 {bucket.unknown}
                            </span>
                          </div>
                          <div
                            className="flex h-2 rounded-full overflow-hidden bg-gh-canvas-inset transition-all duration-300"
                            style={{
                              width:
                                bucketTotal === 0
                                  ? "4%"
                                  : `${(bucketTotal / maxBucketTotal) * 100}%`,
                            }}
                          >
                            {bucket.valid > 0 && (
                              <div
                                className="h-full bg-gh-success"
                                style={{ width: `${(bucket.valid / bucketTotal) * 100}%` }}
                              />
                            )}
                            {bucket.invalid > 0 && (
                              <div
                                className="h-full bg-gh-danger"
                                style={{ width: `${(bucket.invalid / bucketTotal) * 100}%` }}
                              />
                            )}
                            {bucket.unknown > 0 && (
                              <div
                                className="h-full bg-gh-text-muted/40"
                                style={{ width: `${(bucket.unknown / bucketTotal) * 100}%` }}
                              />
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </Card>
                <Card className="p-4">
                  <h3 className="text-sm font-semibold text-gh-text mb-3">按服务商分布</h3>
                  <div className="space-y-2">
                    {stats.by_provider.map((entry) => (
                      <div key={entry.provider} className="flex items-center gap-2">
                        <span className="w-24 shrink-0 truncate text-[11px] text-gh-text-secondary">
                          {entry.provider || "(未知)"}
                        </span>
                        <div className="flex-1 h-2 rounded-full bg-gh-canvas-inset overflow-hidden">
                          <div
                            className="h-full rounded-full bg-gh-accent/70 transition-all duration-300"
                            style={{ width: `${(entry.count / maxProviderCount) * 100}%` }}
                          />
                        </div>
                        <span className="w-10 shrink-0 text-right text-[11px] text-gh-text tabular-nums">
                          {entry.count}
                        </span>
                      </div>
                    ))}
                    {stats.by_provider.length === 0 && (
                      <div className="text-xs text-gh-text-muted py-4 text-center">暂无账号</div>
                    )}
                  </div>
                </Card>
              </div>

              {/* 取号 + 巡检 */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <Card className="p-4">
                  <h3 className="text-sm font-semibold text-gh-text flex items-center gap-2 mb-3">
                    <IconSearch size={14} /> 按存活天数取号
                  </h3>
                  <div className="flex items-center gap-1.5">
                    <input
                      value={minDays}
                      onChange={(e) => setMinDays(e.target.value.replace(/[^\d]/g, ""))}
                      placeholder="最小天数"
                      inputMode="numeric"
                      className="w-full min-w-0 bg-gh-canvas-inset border border-gh-border rounded-md px-2.5 py-1.5 text-sm text-gh-text placeholder-gh-text-secondary focus:outline-none focus:border-gh-accent"
                    />
                    <span className="text-gh-text-muted text-sm">~</span>
                    <input
                      value={maxDays}
                      onChange={(e) => setMaxDays(e.target.value.replace(/[^\d]/g, ""))}
                      placeholder="最大天数"
                      inputMode="numeric"
                      className="w-full min-w-0 bg-gh-canvas-inset border border-gh-border rounded-md px-2.5 py-1.5 text-sm text-gh-text placeholder-gh-text-secondary focus:outline-none focus:border-gh-accent"
                    />
                    <button
                      onClick={() => void handlePick()}
                      disabled={picking}
                      className="shrink-0 px-3 py-1.5 rounded-md text-sm font-medium text-gh-accent bg-gh-accent/10 border border-gh-accent/30 hover:bg-gh-accent/20 transition-colors disabled:opacity-50"
                    >
                      {picking ? "查询中" : "查询"}
                    </button>
                  </div>
                  <p className="mt-2 text-[11px] text-gh-text-muted">
                    按初次导入时间 (created_at) 过滤; 例如取「已导入满 10 天」填最小 10 即可。
                  </p>
                  {picked && (
                    <div className="mt-3 space-y-2 rounded-md border border-gh-border bg-gh-canvas-inset p-2.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-gh-text-secondary">
                          {minDays || "不限"} ~ {maxDays || "不限"} 天
                        </span>
                        <span className="font-semibold text-gh-text tabular-nums">
                          {picked.length} 个
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-[11px]">
                        <span className="text-gh-success tabular-nums">有效 {pickedValid}</span>
                        <span className="text-gh-danger tabular-nums">失效 {pickedInvalid}</span>
                        <button
                          onClick={() => void copyPicked()}
                          disabled={picked.length === 0}
                          className="ml-auto inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-gh-accent border border-gh-accent/30 hover:bg-gh-accent/10 transition-colors disabled:opacity-40"
                          title="复制满足条件的所有主邮箱地址"
                        >
                          <IconCopy size={11} /> 复制邮箱
                        </button>
                      </div>
                    </div>
                  )}
                </Card>
                <Card className="p-4">
                  <h3 className="text-sm font-semibold text-gh-text flex items-center gap-2 mb-3">
                    <IconDatabase size={14} /> 凭证刷新与巡检
                  </h3>
                  <PatrolPanel />
                </Card>
              </div>

              {stats.last_refresh && (
                <div className="flex items-center gap-1.5 text-[11px] text-gh-text-muted">
                  <IconClock size={11} />
                  最近一次凭证刷新: {formatRelativeTime(stats.last_refresh)} · 刷新失败账号
                  {stats.failed_refresh} 个（可到「刷新日志」查看详情）
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
