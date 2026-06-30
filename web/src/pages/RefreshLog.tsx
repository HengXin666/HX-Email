import { AnimatePresence, motion } from "framer-motion";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import {
  IconActivity,
  IconAlertTriangle,
  IconCheck,
  IconClock,
  IconKey,
  IconMail,
  IconRefresh,
  IconX,
} from "../components/icons";
import { Topbar } from "../components/layout";
import { Pagination } from "../components/ui/Pagination";
import { Badge, Button, Modal } from "../components/ui/Primitives";
import { StatCard } from "../components/ui/StatCard";
import { EmptyState, LoadingState } from "../components/ui/StateDisplay";
import { useToast } from "../components/ui/Toast";
import { usePagination } from "../hooks/usePagination";
import type { InvalidTokenCandidate, RefreshLog, RefreshStats } from "../types";
import { formatRelativeTime } from "../utils/time";

const PAGE_SIZE = 20;

const STATUS_COLORS: Record<string, string> = {
  success: "#3fb950",
  failed: "#f85149",
  pending: "#d29922",
};

const STATUS_LABELS: Record<string, string> = {
  success: "成功",
  failed: "失败",
  pending: "进行中",
};

const STATUS_ICONS: Record<string, React.FC<{ size?: number }>> = {
  success: IconCheck,
  failed: IconX,
  pending: IconClock,
};

export const RefreshLogPage: React.FC = () => {
  const { toast } = useToast();
  const [logs, setLogs] = useState<RefreshLog[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<RefreshStats | null>(null);
  const [candidates, setCandidates] = useState<InvalidTokenCandidate[]>([]);
  const [statusFilter, setStatusFilter] = useState<"all" | "success" | "failed">("all");
  const [loading, setLoading] = useState(true);
  const [selectedLog, setSelectedLog] = useState<RefreshLog | null>(null);
  const [showCandidates, setShowCandidates] = useState(false);
  const [candidatesLoading, setCandidatesLoading] = useState(false);

  const pagination = usePagination({ pageSize: PAGE_SIZE, total });

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const [logRes, statsRes] = await Promise.all([
        api.getRefreshLogs(PAGE_SIZE, pagination.offset),
        api.getRefreshStats(),
      ]);
      setLogs(logRes.logs);
      setTotal(logRes.total);
      setStats(statsRes);
    } catch (err: unknown) {
      toast((err as { message?: string }).message || "加载失败", "error");
    } finally {
      setLoading(false);
    }
  }, [pagination.offset, toast]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const handleLoadCandidates = async () => {
    setShowCandidates(true);
    setCandidatesLoading(true);
    try {
      const res = await api.getInvalidTokenCandidates(200, 0);
      setCandidates(res.candidates);
    } catch (err: unknown) {
      toast((err as { message?: string }).message || "加载失败", "error");
    } finally {
      setCandidatesLoading(false);
    }
  };

  const filteredLogs = useMemo(() => {
    if (statusFilter === "all") return logs;
    return logs.filter((l) => l.status === statusFilter);
  }, [logs, statusFilter]);

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
      <Topbar
        title="刷新日志"
        subtitle="Token 刷新历史记录"
        actions={
          <Button variant="secondary" onClick={loadLogs} loading={loading}>
            <IconRefresh size={14} /> 刷新
          </Button>
        }
      />

      <div className="flex-1 overflow-auto p-6">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="max-w-7xl mx-auto space-y-5"
        >
          {/* Stats Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label="总刷新次数"
              value={stats?.total ?? 0}
              icon={IconActivity}
              color="#58a6ff"
            />
            <StatCard label="成功" value={stats?.success ?? 0} icon={IconCheck} color="#3fb950" />
            <StatCard label="失败" value={stats?.failed ?? 0} icon={IconX} color="#f85149" />
            <StatCard
              label="疑似失效 Token"
              value={stats?.pending ?? 0}
              icon={IconAlertTriangle}
              color="#d29922"
            />
          </div>

          {/* Filter Bar */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 bg-gh-canvas-subtle border border-gh-border rounded-lg p-1">
              {(["all", "success", "failed"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => {
                    setStatusFilter(f);
                    pagination.reset();
                  }}
                  className={`px-3 py-1.5 text-sm font-medium rounded-md transition-all ${
                    statusFilter === f
                      ? "bg-gh-canvas-inset text-gh-text shadow-sm"
                      : "text-gh-text-muted hover:text-gh-text"
                  }`}
                >
                  {f === "all" ? "全部" : f === "success" ? "成功" : "失败"}
                </button>
              ))}
            </div>
            <Button variant="secondary" onClick={handleLoadCandidates}>
              <IconAlertTriangle size={14} /> 查看失效 Token
            </Button>
          </div>

          {/* Log Table */}
          <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle overflow-hidden">
            <div className="flex items-center px-4 py-2.5 border-b border-gh-border bg-gh-canvas-inset text-xs font-semibold text-gh-text-muted uppercase tracking-wider">
              <div className="w-8 shrink-0">#</div>
              <div className="flex-1 min-w-0">邮箱</div>
              <div className="w-20 shrink-0 text-center">状态</div>
              <div className="flex-1 min-w-0 hidden md:block">消息</div>
              <div className="w-32 shrink-0 text-right hidden sm:block">时间</div>
            </div>

            <div className="divide-y divide-gh-border/50">
              <AnimatePresence mode="wait">
                {loading ? (
                  <LoadingState />
                ) : filteredLogs.length === 0 ? (
                  <EmptyState message="暂无刷新记录" />
                ) : (
                  filteredLogs.map((log, i) => {
                    const StatusIcon = STATUS_ICONS[log.status] || IconClock;
                    const color = STATUS_COLORS[log.status] || "#6e7681";
                    return (
                      <motion.div
                        key={log.id}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.02 }}
                        onClick={() => {
                          if (log.status === "failed" && log.error_detail) {
                            setSelectedLog(log);
                          }
                        }}
                        className={`flex items-center px-4 py-3 text-sm hover:bg-gh-border/20 transition-colors ${
                          log.status === "failed" && log.error_detail ? "cursor-pointer" : ""
                        }`}
                      >
                        <div className="w-8 shrink-0 text-gh-text-secondary text-xs tabular-nums">
                          {pagination.offset + i + 1}
                        </div>
                        <div className="flex-1 min-w-0 flex items-center gap-2">
                          <IconMail size={13} className="text-gh-text-muted shrink-0" />
                          <span className="text-gh-text truncate font-mono text-xs">
                            {log.email}
                          </span>
                        </div>
                        <div className="w-20 shrink-0 flex justify-center">
                          <Badge color={color}>
                            <StatusIcon size={10} />
                            <span>{STATUS_LABELS[log.status] || log.status}</span>
                          </Badge>
                        </div>
                        <div className="flex-1 min-w-0 hidden md:block">
                          <span className="text-gh-text-secondary text-xs truncate block">
                            {log.message || "—"}
                          </span>
                        </div>
                        <div className="w-32 shrink-0 text-right hidden sm:block">
                          <span className="text-xs text-gh-text-secondary flex items-center justify-end gap-1">
                            <IconClock size={10} />
                            {formatRelativeTime(log.started_at || log.created_at)}
                          </span>
                        </div>
                      </motion.div>
                    );
                  })
                )}
              </AnimatePresence>
            </div>
          </div>

          <Pagination
            currentPage={pagination.page}
            totalPages={pagination.totalPages}
            hasPrev={pagination.hasPrev}
            hasNext={pagination.hasNext}
            onPrev={pagination.goPrev}
            onNext={pagination.goNext}
          />
        </motion.div>
      </div>

      {/* Error Detail Modal */}
      <Modal open={!!selectedLog} onClose={() => setSelectedLog(null)} title="刷新失败详情">
        {selectedLog && (
          <div className="space-y-3">
            <div className="rounded-md border border-gh-border bg-gh-canvas-inset p-3">
              <div className="text-xs text-gh-text-secondary mb-1">邮箱地址</div>
              <div className="text-sm font-mono text-gh-text">{selectedLog.email}</div>
            </div>
            <div className="rounded-md border border-gh-border bg-gh-canvas-inset p-3">
              <div className="text-xs text-gh-text-secondary mb-1">失败原因</div>
              <div className="text-sm text-gh-text">{selectedLog.message || "未知错误"}</div>
            </div>
            {selectedLog.error_detail && (
              <div className="rounded-md border border-gh-danger/30 bg-gh-danger/5 p-3">
                <div className="text-xs text-gh-danger mb-1 font-medium flex items-center gap-1">
                  <IconAlertTriangle size={12} /> 错误详情
                </div>
                <pre className="text-xs text-gh-danger whitespace-pre-wrap break-all font-mono">
                  {selectedLog.error_detail}
                </pre>
              </div>
            )}
            <div className="flex items-center gap-4 text-xs text-gh-text-secondary">
              <span>开始: {formatRelativeTime(selectedLog.started_at)}</span>
              <span>结束: {formatRelativeTime(selectedLog.completed_at)}</span>
            </div>
          </div>
        )}
      </Modal>

      {/* Invalid Token Candidates Modal */}
      <Modal
        open={showCandidates}
        onClose={() => setShowCandidates(false)}
        title="疑似失效 Token 账户"
        size="lg"
      >
        <div className="space-y-2">
          {candidatesLoading ? (
            <LoadingState />
          ) : candidates.length === 0 ? (
            <EmptyState message="暂无疑似失效 Token" />
          ) : (
            candidates.map((c, i) => (
              <motion.div
                key={c.account_id}
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03 }}
                className="rounded-lg border border-gh-border bg-gh-canvas-inset p-3"
              >
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-md bg-gh-danger/10 text-gh-danger flex items-center justify-center shrink-0">
                    <IconKey size={14} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gh-text font-mono">{c.email}</div>
                    <div className="text-xs text-gh-text-secondary mt-0.5">
                      Account ID: {c.account_id}
                    </div>
                    {c.error_detail && (
                      <pre className="mt-2 text-xs text-gh-danger whitespace-pre-wrap break-all font-mono bg-gh-danger/5 border border-gh-danger/20 rounded p-2">
                        {c.error_detail}
                      </pre>
                    )}
                    <div className="mt-1.5 text-xs text-gh-text-secondary flex items-center gap-1">
                      <IconClock size={10} />
                      最后失败: {formatRelativeTime(c.last_failed_at)}
                    </div>
                  </div>
                </div>
              </motion.div>
            ))
          )}
        </div>
      </Modal>
    </div>
  );
};
