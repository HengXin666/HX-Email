import { AnimatePresence, motion } from "framer-motion";
import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { IconClock, IconRefresh, IconServer } from "../components/icons";
import { Topbar } from "../components/layout";
import { FilterSelect } from "../components/ui/FilterSelect";
import { Pagination } from "../components/ui/Pagination";
import { Badge, Button } from "../components/ui/Primitives";
import { EmptyState, LoadingState } from "../components/ui/StateDisplay";
import { useToast } from "../components/ui/Toast";
import { usePagination } from "../hooks/usePagination";
import type { AuditLogEntry } from "../types";
import { formatDateTimeFull } from "../utils/time";

const PAGE_SIZE = 50;

const ACTION_COLORS: Record<string, string> = {
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
  logout: "#6e7681",
  add_to_pool: "#3fb950",
  remove_from_pool: "#f85149",
  cooldown: "#a371f7",
};

const ACTION_OPTIONS = [
  { value: "create", label: "create" },
  { value: "update", label: "update" },
  { value: "delete", label: "delete" },
  { value: "claim", label: "claim" },
  { value: "release", label: "release" },
  { value: "complete", label: "complete" },
  { value: "freeze", label: "freeze" },
  { value: "unfreeze", label: "unfreeze" },
  { value: "retire", label: "retire" },
  { value: "login", label: "login" },
  { value: "logout", label: "logout" },
];

const RESOURCE_TYPE_OPTIONS = [
  { value: "account", label: "account" },
  { value: "pool_entry", label: "pool_entry" },
  { value: "email", label: "email" },
  { value: "platform", label: "platform" },
  { value: "binding", label: "binding" },
  { value: "token", label: "token" },
  { value: "user", label: "user" },
  { value: "setting", label: "setting" },
];

export const AuditLog: React.FC = () => {
  const { toast } = useToast();
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [actionFilter, setActionFilter] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const pagination = usePagination({ pageSize: PAGE_SIZE, total });

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = {
        limit: PAGE_SIZE,
        offset: pagination.offset,
      };
      if (actionFilter) params.action = actionFilter;
      if (resourceType) params.resource_type = resourceType;

      const res = await api.getAuditLogs(params);
      setLogs(res.logs);
      setTotal(res.total);
    } catch (err: unknown) {
      toast((err as { message?: string }).message || "加载失败", "error");
    } finally {
      setLoading(false);
    }
  }, [pagination.offset, actionFilter, resourceType, toast]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
      <Topbar
        title="审计日志"
        subtitle="系统操作审计记录"
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
          {/* Filter Bar */}
          <div className="flex items-center gap-3">
            <FilterSelect
              value={actionFilter}
              onChange={(v) => {
                setActionFilter(v);
                pagination.reset();
              }}
              options={ACTION_OPTIONS}
              placeholder="全部操作"
            />
            <FilterSelect
              value={resourceType}
              onChange={(v) => {
                setResourceType(v);
                pagination.reset();
              }}
              options={RESOURCE_TYPE_OPTIONS}
              placeholder="全部资源类型"
              icon={IconServer}
            />
          </div>

          {/* Log Table */}
          <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle overflow-hidden">
            <div className="flex items-center px-4 py-2.5 border-b border-gh-border bg-gh-canvas-inset text-xs font-semibold text-gh-text-muted uppercase tracking-wider">
              <div className="w-8 shrink-0">#</div>
              <div className="flex-1 min-w-0">时间</div>
              <div className="w-20 shrink-0 text-center">用户</div>
              <div className="w-24 shrink-0 text-center">操作</div>
              <div className="w-24 shrink-0 text-center hidden md:block">资源类型</div>
              <div className="w-20 shrink-0 text-center hidden md:block">资源ID</div>
              <div className="flex-1 min-w-0 hidden lg:block">详情</div>
              <div className="w-36 shrink-0 text-right hidden sm:block">IP</div>
            </div>

            <div className="divide-y divide-gh-border/50">
              <AnimatePresence mode="wait">
                {loading ? (
                  <LoadingState />
                ) : logs.length === 0 ? (
                  <EmptyState message="暂无审计记录" />
                ) : (
                  logs.map((log, i) => {
                    const actionColor = ACTION_COLORS[log.action] || "#6e7681";
                    const isExpanded = expandedId === log.id;
                    return (
                      <motion.div
                        key={log.id}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.01 }}
                      >
                        <div
                          onClick={() => setExpandedId(isExpanded ? null : log.id)}
                          className="flex items-center px-4 py-3 text-sm hover:bg-gh-border/20 transition-colors cursor-pointer"
                        >
                          <div className="w-8 shrink-0 text-gh-text-secondary text-xs tabular-nums">
                            {pagination.offset + i + 1}
                          </div>
                          <div className="flex-1 min-w-0 flex items-center gap-1.5">
                            <IconClock size={12} className="text-gh-text-muted shrink-0" />
                            <span className="text-xs text-gh-text-secondary font-mono">
                              {formatDateTimeFull(log.created_at)}
                            </span>
                          </div>
                          <div className="w-20 shrink-0 text-center">
                            <span className="text-xs text-gh-text-secondary tabular-nums">
                              #{log.user_id}
                            </span>
                          </div>
                          <div className="w-24 shrink-0 flex justify-center">
                            <Badge color={actionColor}>{log.action}</Badge>
                          </div>
                          <div className="w-24 shrink-0 text-center hidden md:block">
                            <span className="text-xs text-gh-text-secondary">
                              {log.resource_type}
                            </span>
                          </div>
                          <div className="w-20 shrink-0 text-center hidden md:block">
                            <span className="text-xs text-gh-text-secondary tabular-nums">
                              #{log.resource_id}
                            </span>
                          </div>
                          <div className="flex-1 min-w-0 hidden lg:block">
                            <span className="text-xs text-gh-text-secondary truncate block">
                              {log.detail || "--"}
                            </span>
                          </div>
                          <div className="w-36 shrink-0 text-right hidden sm:block">
                            <span className="text-xs text-gh-text-muted font-mono">
                              {log.ip_address || "--"}
                            </span>
                          </div>
                        </div>

                        {/* Expanded Detail */}
                        <AnimatePresence>
                          {isExpanded && (
                            <motion.div
                              initial={{ height: 0, opacity: 0 }}
                              animate={{ height: "auto", opacity: 1 }}
                              exit={{ height: 0, opacity: 0 }}
                              transition={{ duration: 0.2 }}
                              className="overflow-hidden"
                            >
                              <div className="px-4 py-3 bg-gh-canvas-inset border-t border-gh-border/50">
                                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                                  <div>
                                    <div className="text-[10px] font-semibold text-gh-text-muted uppercase tracking-wider mb-0.5">
                                      操作
                                    </div>
                                    <div className="text-sm text-gh-text">{log.action}</div>
                                  </div>
                                  <div>
                                    <div className="text-[10px] font-semibold text-gh-text-muted uppercase tracking-wider mb-0.5">
                                      资源类型
                                    </div>
                                    <div className="text-sm text-gh-text">{log.resource_type}</div>
                                  </div>
                                  <div>
                                    <div className="text-[10px] font-semibold text-gh-text-muted uppercase tracking-wider mb-0.5">
                                      资源 ID
                                    </div>
                                    <div className="text-sm text-gh-text tabular-nums">
                                      {log.resource_id}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-[10px] font-semibold text-gh-text-muted uppercase tracking-wider mb-0.5">
                                      用户 ID
                                    </div>
                                    <div className="text-sm text-gh-text tabular-nums">
                                      {log.user_id}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-[10px] font-semibold text-gh-text-muted uppercase tracking-wider mb-0.5">
                                      IP 地址
                                    </div>
                                    <div className="text-sm text-gh-text font-mono">
                                      {log.ip_address || "--"}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-[10px] font-semibold text-gh-text-muted uppercase tracking-wider mb-0.5">
                                      时间
                                    </div>
                                    <div className="text-sm text-gh-text">
                                      {formatDateTimeFull(log.created_at)}
                                    </div>
                                  </div>
                                  <div className="col-span-2">
                                    <div className="text-[10px] font-semibold text-gh-text-muted uppercase tracking-wider mb-0.5">
                                      详情
                                    </div>
                                    <div className="text-sm text-gh-text">{log.detail || "--"}</div>
                                  </div>
                                </div>
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
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
    </div>
  );
};
