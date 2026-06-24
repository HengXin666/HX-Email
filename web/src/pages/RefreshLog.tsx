import React, { useState, useEffect, useMemo, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Topbar } from '../components/layout'
import { Button, Modal, Badge } from '../components/ui/Primitives'
import { useToast } from '../components/ui/Toast'
import {
  IconMail,
  IconCheck,
  IconX,
  IconClock,
  IconRefresh,
  IconChevronRight,
  IconChevronLeft,
  IconAlertTriangle,
  IconActivity,
  IconKey
} from '../components/icons'
import { api } from '../api/client'
import type { RefreshLog, RefreshStats, InvalidTokenCandidate } from '../types'

const PAGE_SIZE = 20

const STATUS_COLORS: Record<string, string> = {
  success: '#3fb950',
  failed: '#f85149',
  pending: '#d29922'
}

const STATUS_LABELS: Record<string, string> = {
  success: '成功',
  failed: '失败',
  pending: '进行中'
}

const STATUS_ICONS: Record<string, React.FC<{ size?: number }>> = {
  success: IconCheck,
  failed: IconX,
  pending: IconClock
}

const formatTime = (raw: string): string => {
  if (!raw) return '—'
  try {
    const d = new Date(raw)
    const now = Date.now()
    const diff = now - d.getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return '刚刚'
    if (mins < 60) return `${mins} 分钟前`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours} 小时前`
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return raw
  }
}

const StatCard: React.FC<{
  label: string
  value: number
  icon: React.FC<{ size?: number }>
  color: string
}> = ({ label, value, icon: IconComp, color }) => (
  <motion.div
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    className="relative overflow-hidden rounded-xl border border-gh-border bg-gh-canvas-subtle p-4"
  >
    <div
      className="absolute top-0 right-0 w-20 h-20 rounded-full blur-2xl opacity-15"
      style={{ background: color }}
    />
    <div className="relative flex items-start justify-between">
      <div>
        <div className="text-xs text-gh-text-muted mb-1">{label}</div>
        <div className="text-2xl font-bold text-gh-text tabular-nums">{value}</div>
      </div>
      <div
        className="w-9 h-9 rounded-lg flex items-center justify-center"
        style={{ background: color + '20', color }}
      >
        <IconComp size={18} />
      </div>
    </div>
  </motion.div>
)

export const RefreshLogPage: React.FC = () => {
  const { toast } = useToast()
  const [logs, setLogs] = useState<RefreshLog[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<RefreshStats | null>(null)
  const [candidates, setCandidates] = useState<InvalidTokenCandidate[]>([])
  const [offset, setOffset] = useState(0)
  const [statusFilter, setStatusFilter] = useState<'all' | 'success' | 'failed'>('all')
  const [loading, setLoading] = useState(true)
  const [selectedLog, setSelectedLog] = useState<RefreshLog | null>(null)
  const [showCandidates, setShowCandidates] = useState(false)
  const [candidatesLoading, setCandidatesLoading] = useState(false)

  const loadLogs = useCallback(async () => {
    setLoading(true)
    try {
      const [logRes, statsRes] = await Promise.all([
        api.getRefreshLogs(PAGE_SIZE, offset),
        api.getRefreshStats()
      ])
      setLogs(logRes.logs)
      setTotal(logRes.total)
      setStats(statsRes)
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [offset, toast])

  useEffect(() => {
    loadLogs()
  }, [loadLogs])

  const handleLoadCandidates = async () => {
    setShowCandidates(true)
    setCandidatesLoading(true)
    try {
      const res = await api.getInvalidTokenCandidates(200, 0)
      setCandidates(res.candidates)
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setCandidatesLoading(false)
    }
  }

  const filteredLogs = useMemo(() => {
    if (statusFilter === 'all') return logs
    return logs.filter((l) => l.status === statusFilter)
  }, [logs, statusFilter])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="flex-1 flex flex-col min-w-0">
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
            <StatCard
              label="成功"
              value={stats?.success ?? 0}
              icon={IconCheck}
              color="#3fb950"
            />
            <StatCard
              label="失败"
              value={stats?.failed ?? 0}
              icon={IconX}
              color="#f85149"
            />
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
              {(['all', 'success', 'failed'] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setStatusFilter(f)}
                  className={`px-3 py-1.5 text-sm font-medium rounded-md transition-all ${
                    statusFilter === f
                      ? 'bg-gh-canvas-inset text-gh-text shadow-sm'
                      : 'text-gh-text-muted hover:text-gh-text'
                  }`}
                >
                  {f === 'all' ? '全部' : f === 'success' ? '成功' : '失败'}
                </button>
              ))}
            </div>
            <Button variant="secondary" onClick={handleLoadCandidates}>
              <IconAlertTriangle size={14} /> 查看失效 Token
            </Button>
          </div>

          {/* Log Table */}
          <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle overflow-hidden">
            {/* Header */}
            <div className="flex items-center px-4 py-2.5 border-b border-gh-border bg-gh-canvas-inset text-xs font-semibold text-gh-text-muted uppercase tracking-wider">
              <div className="w-8 shrink-0">#</div>
              <div className="flex-1 min-w-0">邮箱</div>
              <div className="w-20 shrink-0 text-center">状态</div>
              <div className="flex-1 min-w-0 hidden md:block">消息</div>
              <div className="w-32 shrink-0 text-right hidden sm:block">时间</div>
            </div>

            {/* Rows */}
            <div className="divide-y divide-gh-border/50">
              <AnimatePresence mode="wait">
                {loading ? (
                  <div className="text-center py-16 text-gh-text-secondary text-sm">
                    加载中...
                  </div>
                ) : filteredLogs.length === 0 ? (
                  <div className="text-center py-16 text-gh-text-secondary text-sm">
                    暂无刷新记录
                  </div>
                ) : (
                  filteredLogs.map((log, i) => {
                    const StatusIcon = STATUS_ICONS[log.status] || IconClock
                    const color = STATUS_COLORS[log.status] || '#6e7681'
                    return (
                      <motion.div
                        key={log.id}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.02 }}
                        onClick={() => {
                          if (log.status === 'failed' && log.error_detail) {
                            setSelectedLog(log)
                          }
                        }}
                        className={`flex items-center px-4 py-3 text-sm hover:bg-gh-border/20 transition-colors ${
                          log.status === 'failed' && log.error_detail ? 'cursor-pointer' : ''
                        }`}
                      >
                        <div className="w-8 shrink-0 text-gh-text-secondary text-xs tabular-nums">
                          {offset + i + 1}
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
                            {log.message || '—'}
                          </span>
                        </div>
                        <div className="w-32 shrink-0 text-right hidden sm:block">
                          <span className="text-xs text-gh-text-secondary flex items-center justify-end gap-1">
                            <IconClock size={10} />
                            {formatTime(log.started_at || log.created_at)}
                          </span>
                        </div>
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

      {/* Error Detail Modal */}
      <Modal
        open={!!selectedLog}
        onClose={() => setSelectedLog(null)}
        title="刷新失败详情"
      >
        {selectedLog && (
          <div className="space-y-3">
            <div className="rounded-md border border-gh-border bg-gh-canvas-inset p-3">
              <div className="text-xs text-gh-text-secondary mb-1">邮箱地址</div>
              <div className="text-sm font-mono text-gh-text">{selectedLog.email}</div>
            </div>
            <div className="rounded-md border border-gh-border bg-gh-canvas-inset p-3">
              <div className="text-xs text-gh-text-secondary mb-1">失败原因</div>
              <div className="text-sm text-gh-text">{selectedLog.message || '未知错误'}</div>
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
              <span>开始: {formatTime(selectedLog.started_at)}</span>
              <span>结束: {formatTime(selectedLog.completed_at)}</span>
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
            <div className="text-center py-8 text-gh-text-secondary text-sm">加载中...</div>
          ) : candidates.length === 0 ? (
            <div className="text-center py-8 text-gh-text-secondary text-sm">
              暂无疑似失效 Token
            </div>
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
                    <div className="text-sm font-medium text-gh-text font-mono">
                      {c.email}
                    </div>
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
                      最后失败: {formatTime(c.last_failed_at)}
                    </div>
                  </div>
                </div>
              </motion.div>
            ))
          )}
        </div>
      </Modal>
    </div>
  )
}
