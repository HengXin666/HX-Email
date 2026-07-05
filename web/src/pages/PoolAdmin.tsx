import { AnimatePresence, motion } from "framer-motion";
import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { IconMail, IconRefresh, IconSearch } from "../components/icons";
import { Topbar } from "../components/layout";
import { ConfirmModal } from "../components/ui/ConfirmModal";
import { FilterSelect } from "../components/ui/FilterSelect";
import { Pagination } from "../components/ui/Pagination";
import { Badge, Button } from "../components/ui/Primitives";
import { EmptyState, LoadingState } from "../components/ui/StateDisplay";
import { useToast } from "../components/ui/Toast";
import { usePagination } from "../hooks/usePagination";
import type { Pagination as PaginationType, PoolAdminAccount } from "../types";
import { formatDateTime } from "../utils/time";

const POOL_STATUS_COLORS: Record<string, string> = {
  available: "#3fb950",
  claimed: "#58a6ff",
  completed: "#a371f7",
  cooling: "#d29922",
  frozen: "#f0883e",
  retired: "#6e7681",
};

const POOL_STATUS_LABELS: Record<string, string> = {
  available: "可用",
  claimed: "已领取",
  completed: "已完成",
  cooling: "冷却中",
  frozen: "已冻结",
  retired: "已退役",
};

const POOL_STATUS_OPTIONS = [
  { value: "available", label: "可用" },
  { value: "claimed", label: "已领取" },
  { value: "completed", label: "已完成" },
  { value: "cooling", label: "冷却中" },
  { value: "frozen", label: "已冻结" },
  { value: "retired", label: "已退役" },
];

const PROVIDER_OPTIONS = [
  { value: "gmail", label: "Gmail" },
  { value: "outlook", label: "Outlook" },
  { value: "yahoo", label: "Yahoo" },
  { value: "icloud", label: "iCloud" },
  { value: "other", label: "其他" },
];

const STATUS_ACTIONS: Record<string, string[]> = {
  available: ["claim", "freeze", "retire", "remove_from_pool"],
  claimed: ["release", "complete", "freeze"],
  completed: ["cooldown", "freeze"],
  cooling: ["claim", "freeze", "retire"],
  frozen: ["unfreeze"],
  retired: ["add_to_pool"],
};

const ACTION_LABELS: Record<string, string> = {
  claim: "领取",
  release: "释放",
  complete: "完成",
  freeze: "冻结",
  unfreeze: "解冻",
  cooldown: "冷却",
  retire: "退役",
  add_to_pool: "加入号池",
  remove_from_pool: "移出号池",
};

const ACTION_COLORS: Record<string, string> = {
  claim: "#58a6ff",
  release: "#d29922",
  complete: "#3fb950",
  freeze: "#f0883e",
  unfreeze: "#3fb950",
  cooldown: "#a371f7",
  retire: "#f85149",
  add_to_pool: "#3fb950",
  remove_from_pool: "#f85149",
};

const DANGER_ACTIONS = new Set(["freeze", "retire", "remove_from_pool"]);

const PAGE_SIZE = 20;

export const PoolAdmin: React.FC = () => {
  const { toast } = useToast();
  const [accounts, setAccounts] = useState<PoolAdminAccount[]>([]);
  const [paginationData, setPaginationData] = useState<PaginationType | null>(null);
  const [loading, setLoading] = useState(true);
  const [poolStatus, setPoolStatus] = useState("");
  const [provider, setProvider] = useState("");
  const [groupId, setGroupId] = useState("");
  const [search, setSearch] = useState("");
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [confirmAction, setConfirmAction] = useState<{
    account: PoolAdminAccount;
    action: string;
  } | null>(null);

  const pagination = usePagination({
    pageSize: PAGE_SIZE,
    total: paginationData?.total_count ?? 0,
  });

  const loadAccounts = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = {
        page: pagination.page,
        page_size: PAGE_SIZE,
      };
      if (poolStatus) params.pool_status = poolStatus;
      if (provider) params.provider = provider;
      if (groupId) params.group_id = groupId;
      if (search) params.search = search;

      const res = await api.listPoolAdminAccounts(params);
      setAccounts(res.accounts);
      setPaginationData(res.pagination);
    } catch (err: unknown) {
      toast((err as { message?: string }).message || "加载失败", "error");
    } finally {
      setLoading(false);
    }
  }, [pagination.page, poolStatus, provider, groupId, search, toast]);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  const getActionTargetId = (account: PoolAdminAccount, action: string): number | null => {
    if (action === "add_to_pool") return account.usable_email_id || account.id;
    return account.entry_id > 0 ? account.entry_id : null;
  };

  const handleAction = async (account: PoolAdminAccount, action: string): Promise<void> => {
    const targetId = getActionTargetId(account, action);
    if (targetId === null) {
      toast("该邮箱没有对应的号池条目，不能执行此操作", "error");
      return;
    }

    setActionLoading(account.id);
    try {
      const res = await api.executePoolAction(targetId, action);
      toast(res.message || `${ACTION_LABELS[action] || action} 成功`, "success");
      await loadAccounts();
    } catch (err: unknown) {
      toast((err as { message?: string }).message || "操作失败", "error");
    } finally {
      setActionLoading(null);
      setConfirmAction(null);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
      <Topbar
        title="邮箱池"
        subtitle="管理邮箱池中的可用邮箱状态"
        actions={
          <Button variant="secondary" onClick={loadAccounts} loading={loading}>
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
          <div className="flex flex-wrap items-center gap-3">
            <FilterSelect
              value={poolStatus}
              onChange={(v) => {
                setPoolStatus(v);
                pagination.reset();
              }}
              options={POOL_STATUS_OPTIONS}
              placeholder="全部状态"
            />

            <FilterSelect
              value={provider}
              onChange={(v) => {
                setProvider(v);
                pagination.reset();
              }}
              options={PROVIDER_OPTIONS}
              placeholder="全部服务商"
            />

            <input
              value={groupId}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                setGroupId(e.target.value);
                pagination.reset();
              }}
              placeholder="分组 ID"
              className="w-24 bg-gh-canvas-subtle border border-gh-border rounded-lg px-3 py-2 text-sm text-gh-text placeholder-gh-text-secondary focus:outline-none focus:border-gh-accent"
            />

            <div className="relative flex-1 min-w-[200px] max-w-sm">
              <IconSearch
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gh-text-muted"
              />
              <input
                value={search}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                  setSearch(e.target.value);
                  pagination.reset();
                }}
                placeholder="搜索邮箱..."
                className="w-full bg-gh-canvas-subtle border border-gh-border rounded-lg pl-9 pr-3 py-2 text-sm text-gh-text placeholder-gh-text-secondary focus:outline-none focus:border-gh-accent"
              />
            </div>
          </div>

          {/* Table */}
          <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle overflow-hidden">
            <div className="flex items-center px-4 py-2.5 border-b border-gh-border bg-gh-canvas-inset text-xs font-semibold text-gh-text-muted uppercase tracking-wider">
              <div className="w-8 shrink-0">#</div>
              <div className="flex-1 min-w-0">邮箱</div>
              <div className="w-24 shrink-0 text-center">服务商</div>
              <div className="w-24 shrink-0 text-center">状态</div>
              <div className="flex-1 min-w-0 hidden md:block">分组</div>
              <div className="flex-1 min-w-0 hidden lg:block">领取者</div>
              <div className="w-36 shrink-0 text-right hidden sm:block">领取时间</div>
              <div className="w-48 shrink-0 text-center">操作</div>
            </div>

            <div className="divide-y divide-gh-border/50">
              <AnimatePresence mode="wait">
                {loading ? (
                  <LoadingState />
                ) : accounts.length === 0 ? (
                  <EmptyState message="暂无号池账号" />
                ) : (
                  accounts.map((acct, i) => {
                    const statusColor = POOL_STATUS_COLORS[acct.pool_status] || "#6e7681";
                    const actions = STATUS_ACTIONS[acct.pool_status] || [];
                    return (
                      <motion.div
                        key={acct.id}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.02 }}
                        className="flex items-center px-4 py-3 text-sm hover:bg-gh-border/20 transition-colors"
                      >
                        <div className="w-8 shrink-0 text-gh-text-secondary text-xs tabular-nums">
                          {(pagination.page - 1) * PAGE_SIZE + i + 1}
                        </div>
                        <div className="flex-1 min-w-0 flex items-center gap-2">
                          <IconMail size={13} className="text-gh-text-muted shrink-0" />
                          <span className="text-gh-text truncate font-mono text-xs">
                            {acct.email}
                          </span>
                        </div>
                        <div className="w-24 shrink-0 text-center">
                          <span className="text-xs text-gh-text-secondary">{acct.provider}</span>
                        </div>
                        <div className="w-24 shrink-0 flex justify-center">
                          <Badge color={statusColor}>
                            {POOL_STATUS_LABELS[acct.pool_status] || acct.pool_status}
                          </Badge>
                        </div>
                        <div className="flex-1 min-w-0 hidden md:block">
                          <span className="text-xs text-gh-text-secondary truncate block">
                            {acct.group_name || "--"}
                          </span>
                        </div>
                        <div className="flex-1 min-w-0 hidden lg:block">
                          <span className="text-xs text-gh-text-secondary truncate block">
                            {acct.claimed_by || "--"}
                          </span>
                        </div>
                        <div className="w-36 shrink-0 text-right hidden sm:block">
                          <span className="text-xs text-gh-text-secondary">
                            {acct.claimed_at ? formatDateTime(acct.claimed_at) : "--"}
                          </span>
                        </div>
                        <div className="w-48 shrink-0 flex items-center justify-center gap-1 flex-wrap">
                          {actions.map((action) => (
                            <button
                              key={action}
                              onClick={() => {
                                if (DANGER_ACTIONS.has(action)) {
                                  setConfirmAction({
                                    account: acct,
                                    action,
                                  });
                                } else {
                                  handleAction(acct, action);
                                }
                              }}
                              disabled={actionLoading === acct.id}
                              className="px-1.5 py-0.5 text-[11px] font-medium rounded border transition-colors hover:brightness-125 disabled:opacity-50"
                              style={{
                                borderColor: ACTION_COLORS[action] + "50",
                                color: ACTION_COLORS[action],
                                backgroundColor: ACTION_COLORS[action] + "10",
                              }}
                            >
                              {actionLoading === acct.id ? "..." : ACTION_LABELS[action] || action}
                            </button>
                          ))}
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

      <ConfirmModal
        open={!!confirmAction}
        title="确认操作"
        message={
          confirmAction
            ? `确定要对账号 #${confirmAction.account.id} 执行 ${ACTION_LABELS[confirmAction.action] || confirmAction.action} 操作吗？`
            : ""
        }
        confirmLabel="确认"
        onConfirm={() => confirmAction && handleAction(confirmAction.account, confirmAction.action)}
        onCancel={() => setConfirmAction(null)}
      />
    </div>
  );
};
