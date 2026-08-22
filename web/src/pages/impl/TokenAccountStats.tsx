import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, streamRefresh } from "../../api/client";
import {
  IconAlertTriangle,
  IconCheck,
  IconClock,
  IconCopy,
  IconKey,
  IconMail,
  IconRefresh,
  IconSearch,
  IconShield,
} from "../../components/icons";
import { useToast } from "../../components/ui/Toast";
import type { EmailAccount, SSERefreshEvent } from "../../types";
import { copyToClipboard } from "../../utils/clipboard";
import { accountAgeDays, accountCredentialState, isOAuthProvider } from "../../utils/credential";
import { formatRelativeTime } from "../../utils/time";

const AGE_BUCKETS: Array<{ label: string; min: number; max: number | null }> = [
  { label: "<7天", min: 0, max: 7 },
  { label: "7-14天", min: 7, max: 14 },
  { label: "14-30天", min: 14, max: 30 },
  { label: "30-60天", min: 30, max: 60 },
  { label: "60-90天", min: 60, max: 90 },
  { label: "90-180天", min: 90, max: 180 },
  { label: "180天+", min: 180, max: null },
];

interface AgeRange {
  min?: number;
  max?: number;
}

const SummaryRow: React.FC<{
  label: string;
  value: number;
  tone?: "neutral" | "success" | "danger" | "muted";
  icon?: React.ReactNode;
}> = ({ label, value, tone = "neutral", icon }) => {
  const toneClass =
    tone === "success"
      ? "text-gh-success"
      : tone === "danger"
        ? "text-gh-danger"
        : tone === "muted"
          ? "text-gh-text-muted"
          : "text-gh-text";
  return (
    <div className="flex items-center justify-between gap-2 rounded-md bg-gh-canvas-inset px-2 py-1.5">
      <span className="flex min-w-0 items-center gap-1.5 text-xs text-gh-text-secondary">
        {icon}
        <span className="truncate">{label}</span>
      </span>
      <span className={`text-sm font-semibold tabular-nums ${toneClass}`}>{value}</span>
    </div>
  );
};

export const TokenAccountStats: React.FC = () => {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [accounts, setAccounts] = useState<EmailAccount[]>([]);
  const [loading, setLoading] = useState(true);
  // 按存活天数取号
  const [minDays, setMinDays] = useState("");
  const [maxDays, setMaxDays] = useState("");
  const [appliedRange, setAppliedRange] = useState<AgeRange | null>(null);
  const [picked, setPicked] = useState<EmailAccount[] | null>(null);
  const [picking, setPicking] = useState(false);
  // 巡检
  const [patrolling, setPatrolling] = useState(false);
  const [patrolProgress, setPatrolProgress] = useState<SSERefreshEvent | null>(null);

  const loadAccounts = useCallback(async (): Promise<void> => {
    try {
      setAccounts(await api.listEmailAccounts());
    } catch (err: any) {
      toast(err.message, "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void loadAccounts();
  }, [loadAccounts]);

  const stats = useMemo(() => {
    let valid = 0;
    let invalid = 0;
    let unknown = 0;
    let oauth = 0;
    let microsoft = 0;
    let google = 0;
    let other = 0;
    let failedRefresh = 0;
    let lastRefresh: string | null = null;
    const ageCounts: number[] = AGE_BUCKETS.map(() => 0);
    let agedAccounts = 0;
    for (const account of accounts) {
      const state = accountCredentialState(account);
      if (state === "valid") valid += 1;
      else if (state === "invalid") invalid += 1;
      else unknown += 1;
      const provider = (account.provider || "").toLowerCase();
      if (isOAuthProvider(provider)) oauth += 1;
      if (provider === "outlook") microsoft += 1;
      else if (provider === "gmail") google += 1;
      else other += 1;
      if (account.refresh_failed_at) failedRefresh += 1;
      if (account.last_refresh_at && (!lastRefresh || account.last_refresh_at > lastRefresh)) {
        lastRefresh = account.last_refresh_at;
      }
      const age = accountAgeDays(account);
      if (age !== null) {
        agedAccounts += 1;
        const index = AGE_BUCKETS.findIndex(
          (bucket) => age >= bucket.min && (bucket.max === null || age < bucket.max),
        );
        if (index >= 0) ageCounts[index] += 1;
      }
    }
    return {
      total: accounts.length,
      oauth,
      valid,
      invalid,
      unknown,
      microsoft,
      google,
      other,
      failedRefresh,
      lastRefresh,
      ageCounts,
      agedAccounts,
    };
  }, [accounts]);

  const runPick = useCallback(
    async (range: AgeRange): Promise<void> => {
      setPicking(true);
      setAppliedRange(range);
      try {
        const pickedAccounts = await api.listEmailAccounts({
          min_age_days: range.min,
          max_age_days: range.max,
        });
        setPicked(pickedAccounts);
      } catch (err: any) {
        toast(err.message, "error");
        setPicked(null);
      } finally {
        setPicking(false);
      }
    },
    [toast],
  );

  const handlePickQuery = (): void => {
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
    void runPick({ min, max });
  };

  const handleBucketClick = (bucket: (typeof AGE_BUCKETS)[number]): void => {
    setMinDays(bucket.min === 0 ? "" : String(bucket.min));
    setMaxDays(bucket.max === null ? "" : String(bucket.max));
    void runPick({ min: bucket.min === 0 ? undefined : bucket.min, max: bucket.max ?? undefined });
  };

  const copyPickedEmails = async (): Promise<void> => {
    if (!picked || picked.length === 0) return;
    const text = picked.map((account) => account.primary_address).join("\n");
    const copied = await copyToClipboard(text);
    toast(
      copied ? `已复制 ${picked.length} 个邮箱地址` : "复制失败，请手动复制",
      copied ? "success" : "error",
    );
  };

  const runPatrolAll = async (): Promise<void> => {
    setPatrolling(true);
    setPatrolProgress(null);
    try {
      await streamRefresh("/email-accounts/refresh-all", {}, (e: SSERefreshEvent) => {
        setPatrolProgress(e);
        if (e.type === "complete") {
          toast(
            `巡查完成: 成功 ${e.success ?? 0}, 失败 ${e.failed ?? 0}`,
            (e.failed ?? 0) > 0 ? "error" : "success",
          );
          setPatrolProgress(null);
        }
      });
      await loadAccounts();
    } catch (err: any) {
      toast(err.message, "error");
    } finally {
      setPatrolling(false);
    }
  };

  const maxAgeCount = Math.max(1, ...stats.ageCounts);
  const pickedValid = picked?.filter((a) => accountCredentialState(a) === "valid").length ?? 0;
  const pickedInvalid = picked?.filter((a) => accountCredentialState(a) === "invalid").length ?? 0;
  const patrolCurrent = patrolProgress?.current ?? 0;
  const patrolTotal = patrolProgress?.total ?? 0;

  return (
    <aside className="w-64 shrink-0 min-h-0 border-r border-gh-border bg-gh-canvas-subtle/50 flex flex-col overflow-hidden">
      <div className="h-12 px-3 flex items-center justify-between border-b border-gh-border shrink-0">
        <span className="text-xs font-semibold text-gh-text-muted uppercase tracking-wider">
          账号统计
        </span>
        <button
          onClick={() => void loadAccounts()}
          className="p-1 rounded-md text-gh-text-muted hover:text-gh-accent hover:bg-gh-accent/10 transition-colors"
          title="刷新统计"
        >
          <IconRefresh size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2.5 space-y-3">
        {/* 概览 */}
        <section className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold text-gh-text-secondary uppercase tracking-wider">
            <IconShield size={12} /> 凭证概览
          </div>
          <SummaryRow label="总账号" value={stats.total} icon={<IconMail size={12} />} />
          <SummaryRow
            label="OAuth 账号"
            value={stats.oauth}
            icon={<IconShield size={12} />}
            tone={stats.oauth > 0 ? "neutral" : "muted"}
          />
          <SummaryRow
            label="Microsoft"
            value={stats.microsoft}
            icon={<IconKey size={12} />}
            tone={stats.microsoft > 0 ? "neutral" : "muted"}
          />
          <SummaryRow
            label="Google"
            value={stats.google}
            icon={<IconKey size={12} />}
            tone={stats.google > 0 ? "neutral" : "muted"}
          />
          <SummaryRow label="凭证有效" value={stats.valid} tone="success" />
          <SummaryRow label="凭证失效" value={stats.invalid} tone="danger" />
          <SummaryRow label="未验证" value={stats.unknown} tone="muted" />
        </section>

        {/* 存活时间分布 */}
        <section className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold text-gh-text-secondary uppercase tracking-wider">
            <IconClock size={12} /> 存活时间分布
          </div>
          <div className="text-[10px] text-gh-text-muted">点击区间按天数取号</div>
          <div className="space-y-1">
            {AGE_BUCKETS.map((bucket, index) => {
              const count = stats.ageCounts[index];
              const active =
                appliedRange?.min === (bucket.min === 0 ? undefined : bucket.min) &&
                appliedRange?.max === (bucket.max ?? undefined);
              return (
                <button
                  key={bucket.label}
                  type="button"
                  onClick={() => handleBucketClick(bucket)}
                  className={`w-full flex items-center gap-2 rounded-md px-1.5 py-1 transition-colors ${
                    active
                      ? "bg-gh-accent/10 text-gh-accent"
                      : "text-gh-text-secondary hover:bg-gh-border/30 hover:text-gh-text"
                  }`}
                  title={`筛选存活 ${bucket.label} 的账号`}
                >
                  <span className="w-14 shrink-0 text-left text-[11px]">{bucket.label}</span>
                  <span className="flex-1 h-1.5 rounded-full bg-gh-canvas-inset overflow-hidden">
                    <span
                      className="block h-full rounded-full bg-gh-accent/70 transition-all duration-300"
                      style={{ width: `${Math.round((count / maxAgeCount) * 100)}%` }}
                    />
                  </span>
                  <span className="w-6 shrink-0 text-right text-[11px] tabular-nums">{count}</span>
                </button>
              );
            })}
          </div>
        </section>

        {/* 按存活天数取号 */}
        <section className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold text-gh-text-secondary uppercase tracking-wider">
            <IconSearch size={12} /> 按天数取号
          </div>
          <div className="flex items-center gap-1.5">
            <input
              value={minDays}
              onChange={(e) => setMinDays(e.target.value.replace(/[^\d]/g, ""))}
              placeholder="最小"
              inputMode="numeric"
              className="w-full min-w-0 bg-gh-canvas-inset border border-gh-border rounded-md px-2 py-1 text-xs text-gh-text placeholder-gh-text-secondary focus:outline-none focus:border-gh-accent"
            />
            <span className="text-gh-text-muted text-xs">~</span>
            <input
              value={maxDays}
              onChange={(e) => setMaxDays(e.target.value.replace(/[^\d]/g, ""))}
              placeholder="最大"
              inputMode="numeric"
              className="w-full min-w-0 bg-gh-canvas-inset border border-gh-border rounded-md px-2 py-1 text-xs text-gh-text placeholder-gh-text-secondary focus:outline-none focus:border-gh-accent"
            />
            <button
              onClick={handlePickQuery}
              disabled={picking}
              className="shrink-0 px-2 py-1 rounded-md text-xs font-medium text-gh-accent bg-gh-accent/10 border border-gh-accent/30 hover:bg-gh-accent/20 transition-colors disabled:opacity-50"
            >
              {picking ? "查询中" : "查询"}
            </button>
          </div>
          {appliedRange && (
            <div className="space-y-1.5 rounded-md border border-gh-border bg-gh-canvas-inset p-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-gh-text-secondary">
                  {appliedRange.min != null ? `≥${appliedRange.min}天` : "不限"}
                  {appliedRange.max != null ? ` 且 <${appliedRange.max}天` : ""}
                </span>
                <span className="font-semibold text-gh-text tabular-nums">
                  {picked?.length ?? 0} 个
                </span>
              </div>
              <div className="flex items-center gap-2 text-[11px]">
                <span className="text-gh-success tabular-nums">有效 {pickedValid}</span>
                <span className="text-gh-danger tabular-nums">失效 {pickedInvalid}</span>
                <button
                  onClick={() => void copyPickedEmails()}
                  disabled={!picked || picked.length === 0}
                  className="ml-auto inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-gh-accent border border-gh-accent/30 hover:bg-gh-accent/10 transition-colors disabled:opacity-40"
                  title="复制满足条件的所有主邮箱地址"
                >
                  <IconCopy size={11} /> 复制邮箱
                </button>
              </div>
            </div>
          )}
        </section>

        {/* 凭证刷新与巡检 */}
        <section className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold text-gh-text-secondary uppercase tracking-wider">
            <IconRefresh size={12} /> 刷新与巡检
          </div>
          <div className="flex items-center justify-between gap-2 rounded-md bg-gh-canvas-inset px-2 py-1.5">
            <span className="flex items-center gap-1.5 text-xs text-gh-text-secondary">
              <IconClock size={12} /> 最近刷新
            </span>
            <span className="text-xs text-gh-text tabular-nums">
              {stats.lastRefresh ? formatRelativeTime(stats.lastRefresh) : "—"}
            </span>
          </div>
          <button
            onClick={() => navigate("/refresh-log")}
            className={`w-full flex items-center justify-between gap-2 rounded-md px-2 py-1.5 transition-colors ${
              stats.failedRefresh > 0
                ? "bg-gh-danger/10 text-gh-danger hover:bg-gh-danger/20"
                : "bg-gh-canvas-inset text-gh-text-secondary hover:bg-gh-border/30 hover:text-gh-text"
            }`}
            title="查看刷新日志"
          >
            <span className="flex items-center gap-1.5 text-xs">
              <IconAlertTriangle size={12} /> 刷新失败
            </span>
            <span className="text-sm font-semibold tabular-nums">{stats.failedRefresh}</span>
          </button>
          <button
            onClick={() => void runPatrolAll()}
            disabled={patrolling}
            className="w-full flex items-center justify-center gap-2 rounded-md px-2 py-1.5 text-xs font-medium text-gh-accent bg-gh-accent/10 border border-gh-accent/30 hover:bg-gh-accent/20 transition-colors disabled:opacity-50"
            title="批量刷新全部账号 Token"
          >
            <IconRefresh size={13} className={patrolling ? "animate-spin" : ""} />
            {patrolling ? "巡查中..." : "巡查全部 Token"}
          </button>
          {patrolling && patrolTotal > 0 && (
            <div className="space-y-1">
              <div className="h-1.5 bg-gh-canvas-inset rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-gh-accent to-gh-purple transition-all duration-300"
                  style={{ width: `${Math.round((patrolCurrent / patrolTotal) * 100)}%` }}
                />
              </div>
              <div className="text-[10px] text-gh-text-secondary tabular-nums">
                {patrolCurrent}/{patrolTotal}
                {patrolProgress?.email ? ` · ${patrolProgress.email}` : ""}
              </div>
            </div>
          )}
          {!loading && stats.total === 0 && (
            <div className="flex items-center gap-1.5 rounded-md border border-dashed border-gh-border px-2 py-2 text-[11px] text-gh-text-muted">
              <IconCheck size={12} /> 暂无账号，先去「可用邮箱」导入
            </div>
          )}
        </section>
      </div>
    </aside>
  );
};
