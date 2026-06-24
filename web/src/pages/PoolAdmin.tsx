import React, { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Topbar } from '../components/layout'
import { Button, Modal, Badge } from '../components/ui/Primitives'
import { useToast } from '../components/ui/Toast'
import {
  IconMail,
  IconRefresh,
  IconChevronRight,
  IconChevronLeft,
  IconSearch,
  IconFilter,
  IconChevronDown
} from '../components/icons'
import { api } from '../api/client'
import type { PoolAdminAccount, Pagination } from '../types'

const PAGE_SIZE = 20

const POOL_STATUS_COLORS: Record<string, string> = {
  available: '#3fb950',
  claimed: '#58a6ff',
  completed: '#a371f7',
  cooling: '#d29922',
  frozen: '#f0883e',
  retired: '#6e7681'
}

const POOL_STATUS_LABELS: Record<string, string> = {
  available: '可用',
  claimed: '已领取',
  completed: '已完成',
  cooling: '冷却中',
  frozen: '已冻结',
  retired: '已退役'
}

const STATUS_ACTIONS: Record<string, string[]> = {
  available: ['claim', 'freeze', 'retire', 'remove_from_pool'],
  claimed: ['release', 'complete', 'freeze'],
  completed: ['cooldown', 'freeze'],
  cooling: ['claim', 'freeze', 'retire'],
  frozen: ['unfreeze'],
  retired: ['add_to_pool']
}

const ACTION_LABELS: Record<string, string> = {
  claim: '领取',
  release: '释放',
  complete: '完成',
  freeze: '冻结',
  unfreeze: '解冻',
  cooldown: '冷却',
  retire: '退役',
  add_to_pool: '加入号池',
  remove_from_pool: '移出号池'
}

const ACTION_COLORS: Record<string, string> = {
  claim: '#58a6ff',
  release: '#d29922',
  complete: '#3fb950',
  freeze: '#f0883e',
  unfreeze: '#3fb950',
  cooldown: '#a371f7',
  retire: '#f85149',
  add_to_pool: '#3fb950',
  remove_from_pool: '#f85149'
}

const DANGER_ACTIONS = new Set(['freeze', 'retire', 'remove_from_pool'])

const formatTime = (raw: string): string => {
  if (!raw) return '--'
  try {
    const d = new Date(raw)
    return d.toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return raw
  }
}

export const PoolAdmin: React.FC = () => {
  const { toast } = useToast()
  const [accounts, setAccounts] = useState<PoolAdminAccount[]>([])
  const [pagination, setPagination] = useState<Pagination | null>(null)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [poolStatus, setPoolStatus] = useState('')
  const [provider, setProvider] = useState('')
  const [groupId, setGroupId] = useState('')
  const [search, setSearch] = useState('')
  const [actionLoading, setActionLoading] = useState<number | null>(null)
  const [confirmAction, setConfirmAction] = useState<{
    accountId: number
    action: string
  } | null>(null)

  const loadAccounts = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, string | number> = {
        page,
        page_size: PAGE_SIZE
      }
      if (poolStatus) params.pool_status = poolStatus
      if (provider) params.provider = provider
      if (groupId) params.group_id = groupId
      if (search) params.search = search

      const res = await api.listPoolAdminAccounts(params)
      setAccounts(res.accounts)
      setPagination(res.pagination)
    } catch (err: unknown) {
      toast((err as { message?: string }).message || '加载失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [page, poolStatus, provider, groupId, search, toast])

  useEffect(() => {
    loadAccounts()
  }, [loadAccounts])

  const handleAction = async (accountId: number, action: string): Promise<void> => {
    setActionLoading(accountId)
    try {
      const res = await api.executePoolAction(accountId, action)
      toast(res.message || `${ACTION_LABELS[action] || action} 成功`, 'success')
      await loadAccounts()
    } catch (err: unknown) {
      toast((err as { message?: string }).message || '操作失败', 'error')
    } finally {
      setActionLoading(null)
      setConfirmAction(null)
    }
  }

  const totalPages: number = pagination?.total_pages ?? 1

  return (
    <div className="flex-1 flex flex-col min-w-0">
      <Topbar
        title="号池管理"
        subtitle="管理邮箱池中的账号状态"
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
            {/* Pool Status Filter */}
            <div className="relative">
              <select
                value={poolStatus}
                onChange={(e: React.ChangeEvent<HTMLSelectElement>) => {
                  setPoolStatus(e.target.value)
                  setPage(1)
                }}
                className="appearance-none bg-gh-canvas-subtle border border-gh-border rounded-lg pl-9 pr-8 py-2 text-sm text-gh-text focus:outline-none focus:border-gh-accent cursor-pointer"
              >
                <option value="">全部状态</option>
                <option value="available">可用</option>
                <option value="claimed">已领取</option>
                <option value="completed">已完成</option>
                <option value="cooling">冷却中</option>
                <option value="frozen">已冻结</option>
                <option value="retired">已退役</option>
              </select>
              <IconFilter
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gh-text-muted pointer-events-none"
              />
              <IconChevronDown
                size={12}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gh-text-muted pointer-events-none"
              />
            </div>

            {/* Provider Filter */}
            <div>
              <select
                value={provider}
                onChange={(e: React.ChangeEvent<HTMLSelectElement>) => {
                  setProvider(e.target.value)
                  setPage(1)
                }}
                className="appearance-none bg-gh-canvas-subtle border border-gh-border rounded-lg px-3 py-2 text-sm text-gh-text focus:outline-none focus:border-gh-accent cursor-pointer"
              >
                <option value="">全部服务商</option>
                <option value="gmail">Gmail</option>
                <option value="outlook">Outlook</option>
                <option value="yahoo">Yahoo</option>
                <option value="icloud">iCloud</option>
                <option value="other">其他</option>
              </select>
            </div>

            {/* Group ID Filter */}
            <div>
              <input
                value={groupId}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                  setGroupId(e.target.value)
                  setPage(1)
                }}
                placeholder="分组 ID"
                className="w-24 bg-gh-canvas-subtle border border-gh-border rounded-lg px-3 py-2 text-sm text-gh-text placeholder-gh-text-secondary focus:outline-none focus:border-gh-accent"
              />
            </div>

            {/* Search */}
            <div className="relative flex-1 min-w-[200px] max-w-sm">
              <IconSearch
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gh-text-muted"
              />
              <input
                value={search}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                  setSearch(e.target.value)
                  setPage(1)
                }}
                placeholder="搜索邮箱..."
                className="w-full bg-gh-canvas-subtle border border-gh-border rounded-lg pl-9 pr-3 py-2 text-sm text-gh-text placeholder-gh-text-secondary focus:outline-none focus:border-gh-accent"
              />
            </div>
          </div>

          {/* Table */}
          <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle overflow-hidden">
            {/* Header */}
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

            {/* Rows */}
            <div className="divide-y divide-gh-border/50">
              <AnimatePresence mode="wait">
                {loading ? (
                  <div className="text-center py-16 text-gh-text-secondary text-sm">
                    加载中...
                  </div>
                ) : accounts.length === 0 ? (
                  <div className="text-center py-16 text-gh-text-secondary text-sm">
                    暂无号池账号
                  </div>
                ) : (
                  accounts.map((acct, i) => {
                    const statusColor =
                      POOL_STATUS_COLORS[acct.pool_status] || '#6e7681'
                    const actions = STATUS_ACTIONS[acct.pool_status] || []
                    return (
                      <motion.div
                        key={acct.id}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.02 }}
                        className="flex items-center px-4 py-3 text-sm hover:bg-gh-border/20 transition-colors"
                      >
                        <div className="w-8 shrink-0 text-gh-text-secondary text-xs tabular-nums">
                          {(page - 1) * PAGE_SIZE + i + 1}
                        </div>
                        <div className="flex-1 min-w-0 flex items-center gap-2">
                          <IconMail
                            size={13}
                            className="text-gh-text-muted shrink-0"
                          />
                          <span className="text-gh-text truncate font-mono text-xs">
                            {acct.email}
                          </span>
                        </div>
                        <div className="w-24 shrink-0 text-center">
                          <span className="text-xs text-gh-text-secondary">
                            {acct.provider}
                          </span>
                        </div>
                        <div className="w-24 shrink-0 flex justify-center">
                          <Badge color={statusColor}>
                            {POOL_STATUS_LABELS[acct.pool_status] ||
                              acct.pool_status}
                          </Badge>
                        </div>
                        <div className="flex-1 min-w-0 hidden md:block">
                          <span className="text-xs text-gh-text-secondary truncate block">
                            {acct.group_name || '--'}
                          </span>
                        </div>
                        <div className="flex-1 min-w-0 hidden lg:block">
                          <span className="text-xs text-gh-text-secondary truncate block">
                            {acct.claimed_by || '--'}
                          </span>
                        </div>
                        <div className="w-36 shrink-0 text-right hidden sm:block">
                          <span className="text-xs text-gh-text-secondary">
                            {acct.claimed_at ? formatTime(acct.claimed_at) : '--'}
                          </span>
                        </div>
                        <div className="w-48 shrink-0 flex items-center justify-center gap-1 flex-wrap">
                          {actions.map((action) => (
                            <button
                              key={action}
                              onClick={() => {
                                if (DANGER_ACTIONS.has(action)) {
                                  setConfirmAction({
                                    accountId: acct.id,
                                    action
                                  })
                                } else {
                                  handleAction(acct.id, action)
                                }
                              }}
                              disabled={actionLoading === acct.id}
                              className="px-1.5 py-0.5 text-[11px] font-medium rounded border transition-colors hover:brightness-125 disabled:opacity-50"
                              style={{
                                borderColor: ACTION_COLORS[action] + '50',
                                color: ACTION_COLORS[action],
                                backgroundColor:
                                  ACTION_COLORS[action] + '10'
                              }}
                            >
                              {actionLoading === acct.id
                                ? '...'
                                : ACTION_LABELS[action] || action}
                            </button>
                          ))}
                        </div>
                      </motion.div>
                    )
                  })
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-3">
              <Button
                variant="ghost"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage(Math.max(1, page - 1))}
              >
                <IconChevronLeft size={14} /> 上一页
              </Button>
              <span className="text-sm text-gh-text-secondary tabular-nums">
                第 {page} / {totalPages} 页
              </span>
              <Button
                variant="ghost"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
              >
                下一页 <IconChevronRight size={14} />
              </Button>
            </div>
          )}
        </motion.div>
      </div>

      {/* Confirm Action Modal */}
      <Modal
        open={!!confirmAction}
        onClose={() => setConfirmAction(null)}
        title="确认操作"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmAction(null)}>
              取消
            </Button>
            <Button
              variant="danger"
              onClick={() =>
                confirmAction &&
                handleAction(confirmAction.accountId, confirmAction.action)
              }
            >
              确认
            </Button>
          </>
        }
      >
        {confirmAction && (
          <div className="text-sm text-gh-text">
            确定要对账号{' '}
            <span className="font-mono text-gh-accent">
              #{confirmAction.accountId}
            </span>{' '}
            执行
            <span className="font-semibold text-gh-danger">
              {' '}
              {ACTION_LABELS[confirmAction.action] || confirmAction.action}
            </span>{' '}
            操作吗？
          </div>
        )}
      </Modal>
    </div>
  )
}
