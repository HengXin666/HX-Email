import { motion } from "framer-motion";
import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import {
  IconActivity,
  IconChevronRight,
  IconClock,
  IconDatabase,
  IconMail,
  IconRefresh,
  IconServer,
  IconShield,
  IconUser,
  IconZap,
} from "../components/icons";
import { Topbar } from "../components/layout";
import { Badge } from "../components/ui/Primitives";
import { StatCard } from "../components/ui/StatCard";
import { useToast } from "../components/ui/Toast";
import { useApp } from "../store/AppContext";
import type { ActivityStats, PoolStats, VerificationStats } from "../types";
import { PlatformLogo } from "./impl/PlatformLogo";

export const Overview: React.FC = () => {
  const { overview, emails, groups, platforms, refreshOverview } = useApp();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [verificationStats, setVerificationStats] = useState<VerificationStats | null>(null);
  const [poolStats, setPoolStats] = useState<PoolStats | null>(null);
  const [activityStats, setActivityStats] = useState<ActivityStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  useEffect(() => {
    refreshOverview();
  }, [refreshOverview]);

  const loadExtraStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const [vRes, pRes, aRes] = await Promise.all([
        api.getVerificationStats(),
        api.getPoolStats(),
        api.getActivityStats(),
      ]);
      setVerificationStats(vRes);
      setPoolStats(pRes);
      setActivityStats(aRes);
    } catch (err: unknown) {
      toast((err as { message?: string }).message || "加载失败", "error");
    } finally {
      setStatsLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadExtraStats();
  }, [loadExtraStats]);

  const recentEmails = emails.slice(0, 5);
  const topPlatforms = platforms.slice(0, 5);

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
      <Topbar title="工作台" subtitle="所有邮箱、平台、任务的总览视图" />

      <div className="flex-1 overflow-auto p-6">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="max-w-7xl mx-auto space-y-6"
        >
          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            <StatCard
              label="可用邮箱"
              value={overview?.usable_email_count ?? 0}
              icon={IconMail}
              color="#58a6ff"
              trend="↑ 活跃"
              onClick={() => navigate("/accounts")}
            />
            <StatCard
              label="邮箱账户"
              value={overview?.account_count ?? 0}
              icon={IconUser}
              color="#a371f7"
              onClick={() => navigate("/accounts")}
            />
            <StatCard
              label="平台"
              value={overview?.platform_count ?? 0}
              icon={IconServer}
              color="#3fb950"
              onClick={() => navigate("/platforms")}
            />
            <StatCard
              label="绑定关系"
              value={overview?.binding_count ?? 0}
              icon={IconActivity}
              color="#d29922"
            />
            <StatCard
              label="临时邮箱"
              value={overview?.temp_email_count ?? 0}
              icon={IconClock}
              color="#f0883e"
              onClick={() => navigate("/temp-mail")}
            />
            <StatCard
              label="邮箱池·可用"
              value={overview?.pool_available_count ?? 0}
              icon={IconDatabase}
              color="#db61a2"
            />
            <StatCard
              label="邮箱池·已领"
              value={overview?.pool_claimed_count ?? 0}
              icon={IconShield}
              color="#f85149"
            />
            <StatCard
              label="验证码记录"
              value={overview?.verification_count ?? 0}
              icon={IconZap}
              color="#6e7681"
            />
          </div>

          {/* Two columns */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* 最近邮箱 */}
            <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gh-text">最近更新的邮箱</h3>
                <button
                  onClick={() => navigate("/accounts")}
                  className="text-xs text-gh-accent hover:underline inline-flex items-center gap-0.5"
                >
                  查看全部 <IconChevronRight size={12} />
                </button>
              </div>
              <div className="space-y-1.5">
                {recentEmails.map((e, i) => (
                  <motion.div
                    key={e.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05 }}
                    className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-gh-border/30 transition-colors"
                  >
                    <div
                      className="w-8 h-8 rounded-md flex items-center justify-center text-xs font-semibold shrink-0"
                      style={{
                        background: (e.group?.color || "#58a6ff") + "20",
                        color: e.group?.color || "#58a6ff",
                      }}
                    >
                      {e.address.slice(0, 1).toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-gh-text truncate">{e.address}</div>
                      <div className="text-xs text-gh-text-secondary truncate">
                        {e.label || "—"} · {e.updated_at}
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>

            {/* 平台分布 */}
            <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gh-text">平台分布</h3>
                <button
                  onClick={() => navigate("/platforms")}
                  className="text-xs text-gh-accent hover:underline inline-flex items-center gap-0.5"
                >
                  管理 <IconChevronRight size={12} />
                </button>
              </div>
              <div className="space-y-2">
                {topPlatforms.map((p, i) => {
                  const max = Math.max(...topPlatforms.map((x) => x.binding_count || 0), 1);
                  const pct = ((p.binding_count || 0) / max) * 100;
                  return (
                    <motion.div
                      key={p.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.05 }}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="flex items-center gap-2 min-w-0">
                          <PlatformLogo name={p.name} size="xs" />
                          <span className="text-sm text-gh-text truncate">{p.name}</span>
                        </span>
                        <span className="text-xs text-gh-text-muted tabular-nums">
                          {p.binding_count || 0} 绑定
                        </span>
                      </div>
                      <div className="h-1.5 bg-gh-canvas-inset rounded-full overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${pct}%` }}
                          transition={{ delay: 0.1 + i * 0.05, duration: 0.5 }}
                          className="h-full bg-gradient-to-r from-gh-accent to-gh-purple rounded-full"
                        />
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* 分组概览 */}
          <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle p-4">
            <h3 className="text-sm font-semibold text-gh-text mb-3">邮箱分组</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
              {groups.map((g, i) => (
                <motion.div
                  key={g.id}
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: i * 0.05 }}
                  whileHover={{ y: -2 }}
                  onClick={() => navigate("/accounts")}
                  className="cursor-pointer rounded-lg border border-gh-border bg-gh-canvas-inset p-3 hover:border-gh-text-muted transition-all"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <div
                      className="w-2.5 h-2.5 rounded-full"
                      style={{
                        background: g.color,
                        boxShadow: `0 0 8px ${g.color}`,
                      }}
                    />
                    <span className="text-sm text-gh-text truncate">{g.name}</span>
                  </div>
                  <div className="text-2xl font-bold text-gh-text tabular-nums">{g.count || 0}</div>
                  <div className="text-xs text-gh-text-secondary">个邮箱</div>
                </motion.div>
              ))}
            </div>
          </div>

          {/* Verification Stats Section */}
          <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gh-text flex items-center gap-2">
                <IconZap size={14} className="text-gh-accent" />
                验证码统计
              </h3>
              <button
                onClick={loadExtraStats}
                className="p-1 rounded-md text-gh-text-muted hover:text-gh-text hover:bg-gh-border/50 transition-colors"
                title="刷新"
              >
                <IconRefresh size={14} />
              </button>
            </div>
            {statsLoading ? (
              <div className="text-center py-6 text-gh-text-secondary text-sm">加载中...</div>
            ) : verificationStats ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="text-center p-3 rounded-lg bg-gh-canvas-inset border border-gh-border">
                  <div className="text-xs text-gh-text-muted mb-1">总提取次数</div>
                  <div className="text-xl font-bold text-gh-text tabular-nums">
                    {verificationStats.total_extractions}
                  </div>
                </div>
                <div className="text-center p-3 rounded-lg bg-gh-canvas-inset border border-gh-border">
                  <div className="text-xs text-gh-text-muted mb-1">成功率</div>
                  <div
                    className="text-xl font-bold tabular-nums"
                    style={{
                      color: verificationStats.success_rate >= 80 ? "#3fb950" : "#d29922",
                    }}
                  >
                    {verificationStats.success_rate}%
                  </div>
                </div>
                <div className="text-center p-3 rounded-lg bg-gh-canvas-inset border border-gh-border">
                  <div className="text-xs text-gh-text-muted mb-1">AI 回退次数</div>
                  <div className="text-xl font-bold text-gh-text tabular-nums">
                    {verificationStats.ai_fallback_count}
                  </div>
                </div>
                <div className="text-center p-3 rounded-lg bg-gh-canvas-inset border border-gh-border">
                  <div className="text-xs text-gh-text-muted mb-1">今日提取</div>
                  <div className="text-xl font-bold text-gh-text tabular-nums">
                    {verificationStats.today_extractions}
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-6 text-gh-text-secondary text-sm">暂无数据</div>
            )}
          </div>

          {/* Pool Stats Section */}
          <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle p-4">
            <h3 className="text-sm font-semibold text-gh-text flex items-center gap-2 mb-3">
              <IconDatabase size={14} className="text-gh-purple" />
              号池分布
            </h3>
            {statsLoading ? (
              <div className="text-center py-6 text-gh-text-secondary text-sm">加载中...</div>
            ) : poolStats ? (
              <div className="space-y-2">
                {[
                  { label: "可用", value: poolStats.available, color: "#3fb950" },
                  { label: "已领取", value: poolStats.claimed, color: "#58a6ff" },
                  {
                    label: "已完成",
                    value: poolStats.completed,
                    color: "#a371f7",
                  },
                  { label: "冷却中", value: poolStats.cooling, color: "#d29922" },
                  { label: "已冻结", value: poolStats.frozen, color: "#f0883e" },
                  { label: "已退役", value: poolStats.retired, color: "#6e7681" },
                ].map((item) => {
                  const maxVal: number = Math.max(
                    ...Object.values(poolStats).filter((v): v is number => typeof v === "number"),
                    1,
                  );
                  const pct: number = (item.value / maxVal) * 100;
                  return (
                    <motion.div key={item.label} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-1.5">
                          <div
                            className="w-2 h-2 rounded-full"
                            style={{ background: item.color }}
                          />
                          <span className="text-sm text-gh-text">{item.label}</span>
                        </div>
                        <span className="text-xs text-gh-text-muted tabular-nums">
                          {item.value}
                        </span>
                      </div>
                      <div className="h-1.5 bg-gh-canvas-inset rounded-full overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${pct}%` }}
                          transition={{ duration: 0.5 }}
                          className="h-full rounded-full"
                          style={{ background: item.color }}
                        />
                      </div>
                    </motion.div>
                  );
                })}
                <div className="pt-2 mt-2 border-t border-gh-border flex justify-between">
                  <span className="text-xs text-gh-text-muted">总计</span>
                  <span className="text-sm font-semibold text-gh-text tabular-nums">
                    {poolStats.total}
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-center py-6 text-gh-text-secondary text-sm">暂无数据</div>
            )}
          </div>

          {/* Activity Feed Section */}
          <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle p-4">
            <h3 className="text-sm font-semibold text-gh-text flex items-center gap-2 mb-3">
              <IconActivity size={14} className="text-gh-orange" />
              近期活动
            </h3>
            {statsLoading ? (
              <div className="text-center py-6 text-gh-text-secondary text-sm">加载中...</div>
            ) : activityStats ? (
              <div>
                <div className="flex items-center gap-4 mb-3 text-xs text-gh-text-secondary">
                  <span>
                    今日操作:{" "}
                    <span className="text-gh-text font-semibold">
                      {activityStats.today_actions}
                    </span>
                  </span>
                  <span>
                    总计:{" "}
                    <span className="text-gh-text font-semibold">
                      {activityStats.total_actions}
                    </span>
                  </span>
                </div>
                {activityStats.recent_actions.length > 0 ? (
                  <div className="space-y-1.5">
                    {activityStats.recent_actions.map((item) => {
                      const actionColors: Record<string, string> = {
                        create: "#3fb950",
                        update: "#58a6ff",
                        delete: "#f85149",
                        claim: "#58a6ff",
                        release: "#d29922",
                        complete: "#3fb950",
                        freeze: "#f0883e",
                        unfreeze: "#3fb950",
                        retire: "#6e7681",
                        login: "#a371f7",
                      };
                      const color: string = actionColors[item.action] || "#6e7681";
                      return (
                        <div
                          key={item.action}
                          className="flex items-center justify-between px-3 py-1.5 rounded-md hover:bg-gh-border/20 transition-colors"
                        >
                          <div className="flex items-center gap-2">
                            <Badge color={color}>{item.action}</Badge>
                          </div>
                          <span className="text-xs text-gh-text-secondary tabular-nums">
                            {item.count} 次
                          </span>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-center py-6 text-gh-text-secondary text-sm">暂无活动</div>
                )}
              </div>
            ) : (
              <div className="text-center py-6 text-gh-text-secondary text-sm">暂无数据</div>
            )}
          </div>
        </motion.div>
      </div>
    </div>
  );
};
