import React, { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Topbar } from '../components/layout'
import { Button, Badge } from '../components/ui/Primitives'
import { useToast } from '../components/ui/Toast'
import {
  IconRefresh,
  IconChevronRight,
  IconChevronLeft,
  IconShield,
  IconClock,
  IconServer,
  IconFilter,
  IconChevronDown
} from '../components/icons'
import { api } from '../api/client'
import type { AuditLogEntry } from '../types'

const PAGE_SIZE = 50

const ACTION_COLORS: Record<string, string> = {
  create: '#3fb950',
  update: '#58a6ff',
  delete: '#f85149',
  claim: '#58a6ff',
  release: '#d29922',
  complete: '#3fb950',
  freeze: '#f0883e',
  unfreeze: '#3fb950',
  retire: '#6e7681',
  login: '#a371f7',
  logout: '#6e7681',
  add_to_pool: '#3fb950',
  remove_from_pool: '#f85149',
  cooldown: '#a371f7'
}

const formatTime = (raw: string): string => {
  if (!raw) return '--'
  try {
    const d = new Date(raw)
    return d.toLocaleString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  } catch {
    return raw
  }
}

export const AuditLog: React.FC = () => {
  const { toast } = useToast()
  const [logs, setLogs] = useState<AuditLogEntry[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [actionFilter, setActionFilter] = useState('')
  const [resourceType, setResourceType] = useState('')
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const loadLogs = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, string | number> = {
        limit: PAGE_SIZE,
        offset
      }
      if (actionFilter) params.action = actionFilter
      if (resourceType) params.resource_type = resourceType

      const res = await api.getAuditLogs(params)
      setLogs(res.logs)
      setTotal(res.total)
    } catch (err: unknown) {
      toast((err as { message?: string }).message || '加载失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [offset, actionFilter, resourceType, toast])

  useEffect(() => {
    loadLogs()
  }, [loadLogs])

  const totalPages: number = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const currentPage: number = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="flex-1 flex flex-col min-w-0">
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
            <div className="relative">
              <select
                value={actionFilter}
                onChange={(e: React.ChangeEvent<HTMLSelectElement>) => {
                  setActionFilter(e.target.value)
                  setOffset(0)
                }}
                className="appearance-none bg-gh-canvas-subtle border border-gh-border rounded-lg pl-9 pr-8 py-2 text-sm text-gh-text focus:outline-none focus:border-gh-accent cursor-pointer"
              >
                <option value="">全部操作</option>
                <option value="create">create</option>
                <option value="update">update</option>
                <option value="delete">delete</option>
                <option value="claim">claim</option>
                <option value="release">release</option>
                <option value="complete">complete</option>
                <option value="freeze">freeze</option>
                <option value="unfreeze">unfreeze</option>
                <option value="retire">retire</option>
                <option value="login">login</option>
                <option value="logout">logout</option>
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
            <div className="relative">
              <select
                value={resourceType}
                onChange={(e: React.ChangeEvent<HTMLSelectElement>) => {
                  setResourceType(e.target.value)
                  setOffset(0)
                }}
                className="appearance-none bg-gh-canvas-subtle border border-gh-border rounded-lg pl-9 pr-8 py-2 text-sm text-gh-text focus:outline-none focus:border-gh-accent cursor-pointer"
              >
                <option value="">全部资源类型</option>
                <option value="account">account</option>
                <option value="pool_entry">pool_entry</option>
                <option value="email">email</option>
                <option value="platform">platform</option>
                <option value="binding">binding</option>
                <option value="token">token</option>
                <option value="user">user</option>
                <option value="setting">setting</option>
              </select>
              <IconServer
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gh-text-muted pointer-events-none"
              />
              <IconChevronDown
                size={12}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gh-text-muted pointer-events-none"
              />
            </div>
          </div>

          {/* Log Table */}
          <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle overflow-hidden">
            {/* Header */}
            <div className="flex items-center px-4 py-2.5 border-b border-gh-border bg-gh-canvas-inset text-xs font-semibold text-gh-text-muted uppercase tracking-wider">
              <div className="w-8 shrink-0">#</div>
              <div className="flex-1 min-w-0">时间</div>
              <div className="w-20 shrink-0 text-center">用户</div>
              <div className="w-24 shrink-0 text-center">操作</div>
              <div className="w-24 shrink-0 text-center hidden md:block">
                资源类型
              </div>
              <div className="w-20 shrink-0 text-center hidden md:block">
                资源ID
              </div>
              <div className="flex-1 min-w-0 hidden lg:block">详情</div>
              <div className="w-36 shrink-0 text-right hidden sm:block">IP</div>
            </div>

            {/* Rows */}
            <div className="divide-y divide-gh-border/50">
              <AnimatePresence mode="wait">
                {loading ? (
                  <div className="text-center py-16 text-gh-text-secondary text-sm">
                    加载中...
                  </div>
                ) : logs.length === 0 ? (
                  <div className="text-center py-16 text-gh-text-secondary text-sm">
                    暂无审计记录
                  </div>
                ) : (
                  logs.map((log, i) => {
                    const actionColor =
                      ACTION_COLORS[log.action] || '#6e7681'
                    const isExpanded = expandedId === log.id
                    return (
                      <motion.div
                        key={log.id}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.01 }}
                      >
                        <div
                          onClick={() =>
                            setExpandedId(isExpanded ? null : log.id)
                          }
                          className="flex items-center px-4 py-3 text-sm hover:bg-gh-border/20 transition-colors cursor-pointer"
                        >
                          <div className="w-8 shrink-0 text-gh-text-secondary text-xs tabular-nums">
                            {offset + i + 1}
                          </div>
                          <div className="flex-1 min-w-0 flex items-center gap-1.5">
                            <IconClock
                              size={12}
                              className="text-gh-text-muted shrink-0"
                            />
                            <span className="text-xs text-gh-text-secondary font-mono">
                              {formatTime(log.created_at)}
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
                              {log.detail || '--'}
                            </span>
                          </div>
                          <div className="w-36 shrink-0 text-right hidden sm:block">
                            <span className="text-xs text-gh-text-muted font-mono">
                              {log.ip_address || '--'}
                            </span>
                          </div>
                        </div>

                        {/* Expanded Detail */}
                        <AnimatePresence>
                          {isExpanded && (
                            <motion.div
                              initial={{ height: 0, opacity: 0 }}
                              animate={{ height: 'auto', opacity: 1 }}
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
                                    <div className="text-sm text-gh-text">
                                      {log.action}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-[10px] font-semibold text-gh-text-muted uppercase tracking-wider mb-0.5">
                                      资源类型
                                    </div>
                                    <div className="text-sm text-gh-text">
                                      {log.resource_type}
                                    </div>
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
                                      {log.ip_address || '--'}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-[10px] font-semibold text-gh-text-muted uppercase tracking-wider mb-0.5">
                                      时间
                                    </div>
                                    <div className="text-sm text-gh-text">
                                      {formatTime(log.created_at)}
                                    </div>
                                  </div>
                                  <div className="col-span-2">
                                    <div className="text-[10px] font-semibold text-gh-text-muted uppercase tracking-wider mb-0.5">
                                      详情
                                    </div>
                                    <div className="text-sm text-gh-text">
                                      {log.detail || '--'}
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </motion.div>
                    )
                  })
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* Pagination */}
          {total > PAGE_SIZE && (
            <div className="flex items-center justify-center gap-3">
              <Button
                variant="ghost"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                <IconChevronLeft size={14} /> 上一页
              </Button>
              <span className="text-sm text-gh-text-secondary tabular-nums">
                第 {currentPage} / {totalPages} 页
              </span>
              <Button
                variant="ghost"
                size="sm"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                下一页 <IconChevronRight size={14} />
              </Button>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  )
}
