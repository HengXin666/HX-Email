import React, { useState, useEffect, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Topbar } from '../components/layout'

// Email body HTML rendering styles
const EMAIL_BODY_STYLE = {
  wordBreak: 'break-word' as const,
  overflowWrap: 'break-word' as const,
  maxWidth: '100%',
} as React.CSSProperties
const OUTLOOK_ALIAS_MANAGE_URL = 'https://account.live.com/names/manage'
import { useApp } from '../store/AppContext'
import { useToast } from '../components/ui/Toast'
import { Button, Modal, Input, Badge, Card, Checkbox, Select } from '../components/ui/Primitives'
import { ConfirmModal } from '../components/ui/ConfirmModal'
import { CopyButton } from '../components/ui/CopyButton'
import { LoadingState, EmptyState } from '../components/ui/StateDisplay'
import {
  IconFolderPlus,
  IconEdit,
  IconTrash,
  IconPlus,
  IconCopy,
  IconCheck,
  IconMail,
  IconKey,
  IconStar,
  IconRefresh,
  IconTag,
  IconSettings,
  IconLink,
  IconClock,
  IconShield,
  IconCode,
  IconAt,
  IconUser,
  IconAlertTriangle,
  IconX
} from '../components/icons'
import { api, streamRefresh } from '../api/client'
import type { UsableEmail, VerificationMatch, SSERefreshEvent, AccountImportResult } from '../types'

const COLORS = [
  '#58a6ff',
  '#3fb950',
  '#a371f7',
  '#f0883e',
  '#f85149',
  '#d29922',
  '#db61a2',
  '#6e7681'
]

// ========== 左侧：分组栏 ==========
const GroupSidebar: React.FC<{
  selectedGroupId: number | null
  onSelect: (id: number | null) => void
}> = ({ selectedGroupId, onSelect }) => {
  const { groups, emails, createGroup, updateGroup, deleteGroup } = useApp()
  const { toast } = useToast()
  const [editingGroup, setEditingGroup] = useState<number | null>(null)
  const [showNew, setShowNew] = useState(false)
  const [newName, setNewName] = useState('')
  const [newColor, setNewColor] = useState(COLORS[0])
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)

  const counts = useMemo(() => {
    const map: Record<number | 'all', number> = { all: emails.length }
    groups.forEach((g) => {
      map[g.id] = emails.filter((e) => e.group?.id === g.id).length
    })
    return map
  }, [groups, emails])

  const handleCreate = async () => {
    if (!newName.trim()) return
    try {
      await createGroup(newName.trim(), newColor)
      toast('分组已创建', 'success')
      setNewName('')
      setShowNew(false)
    } catch (err: any) {
      toast(err.message, 'error')
    }
  }

  const handleDelete = async (id: number) => {
    setDeleteConfirmId(id)
  }

  const confirmDelete = async () => {
    const id = deleteConfirmId
    if (!id) return
    try {
      await deleteGroup(id)
      if (selectedGroupId === id) onSelect(null)
      toast('分组已删除', 'success')
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setDeleteConfirmId(null)
    }
  }

  return (
    <div className="w-44 shrink-0 min-h-0 border-r border-gh-border bg-gh-canvas-subtle/50 flex flex-col overflow-hidden">
      <div className="h-12 px-3 flex items-center justify-between border-b border-gh-border">
        <span className="text-xs font-semibold text-gh-text-muted uppercase tracking-wider">
          分组
        </span>
        <button
          onClick={() => setShowNew(true)}
          className="p-1 rounded-md text-gh-text-muted hover:text-gh-accent hover:bg-gh-accent/10 transition-colors"
        >
          <IconFolderPlus size={14} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
        <button
          onClick={() => onSelect(null)}
          className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors ${
            selectedGroupId === null
              ? 'bg-gh-accent/10 text-gh-accent'
              : 'text-gh-text-muted hover:text-gh-text hover:bg-gh-border/40'
          }`}
        >
          <IconMail size={14} />
          <span className="flex-1 text-left">全部</span>
          <span className="text-xs tabular-nums">{counts.all}</span>
        </button>

        {groups.map((g) => (
          <GroupItem
            key={g.id}
            group={g}
            count={counts[g.id] || 0}
            selected={selectedGroupId === g.id}
            onClick={() => onSelect(g.id)}
            onEdit={() => setEditingGroup(g.id)}
            onDelete={() => handleDelete(g.id)}
          />
        ))}
      </div>

      {/* 创建分组 */}
      <Modal open={showNew} onClose={() => setShowNew(false)} title="创建分组"
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowNew(false)}>取消</Button>
            <Button variant="primary" onClick={handleCreate}>创建</Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input label="分组名称" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="例如：工作" />
          <div>
            <label className="text-xs font-medium text-gh-text-muted block mb-1.5">颜色</label>
            <div className="flex gap-2 flex-wrap">
              {COLORS.map((c) => (
                <button
                  key={c}
                  onClick={() => setNewColor(c)}
                  className={`w-7 h-7 rounded-full transition-all ${
                    newColor === c ? 'ring-2 ring-gh-text ring-offset-2 ring-offset-gh-canvas-subtle scale-110' : ''
                  }`}
                  style={{ background: c }}
                />
              ))}
            </div>
          </div>
        </div>
      </Modal>

      {/* 编辑分组 — key 确保切换分组时状态完全重置 */}
      <EditGroupModal
        key={editingGroup ?? 'new'}
        groupId={editingGroup}
        onClose={() => setEditingGroup(null)}
        onUpdate={updateGroup}
        onDelete={deleteGroup}
      />

      <ConfirmModal
        open={deleteConfirmId !== null}
        title="删除分组"
        message={`确定删除该分组吗？此操作不可撤销。`}
        confirmLabel="删除"
        onConfirm={confirmDelete}
        onCancel={() => setDeleteConfirmId(null)}
      />
    </div>
  )
}

const GroupItem: React.FC<{
  group: any
  count: number
  selected: boolean
  onClick: () => void
  onEdit: () => void
  onDelete: () => void
}> = ({ group, count, selected, onClick, onEdit, onDelete }) => {
  return (
    <div className="relative group">
      <button
        onClick={onClick}
        className={`w-full flex items-center gap-2.5 px-2.5 py-2 pr-14 rounded-md text-sm transition-colors ${
          selected
            ? 'bg-gh-accent/10 text-gh-accent'
            : 'text-gh-text-muted hover:text-gh-text hover:bg-gh-border/40'
        }`}
      >
        <div
          className="w-2.5 h-2.5 rounded-sm shrink-0"
          style={{ background: group.color, boxShadow: selected ? `0 0 6px ${group.color}` : 'none' }}
        />
        <span className="flex-1 text-left truncate">{group.name}</span>
        <span className="text-xs tabular-nums opacity-70">{count}</span>
      </button>
      {/* 编辑 / 删除 — hover 时直接显示，无需二次点击下拉菜单 */}
      <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
        <button
          onClick={(e) => { e.stopPropagation(); onEdit() }}
          className="p-1 rounded-md text-gh-text-muted hover:text-gh-accent hover:bg-gh-accent/10 transition-colors"
          title="编辑分组"
        >
          <IconEdit size={13} />
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete() }}
          className="p-1 rounded-md text-gh-text-muted hover:text-red-400 hover:bg-red-400/10 transition-colors"
          title="删除分组"
        >
          <IconTrash size={13} />
        </button>
      </div>
    </div>
  )
}

const EditGroupModal: React.FC<{
  groupId: number | null
  onClose: () => void
  onUpdate: (id: number, name: string, color: string, proxy_url?: string) => Promise<any>
  onDelete: (id: number) => Promise<any>
}> = ({ groupId, onClose, onUpdate, onDelete }) => {
  const { groups } = useApp()
  const { toast } = useToast()
  const g = groups.find((x) => x.id === groupId)
  const [name, setName] = useState(g?.name || '')
  const [color, setColor] = useState(g?.color || COLORS[0])
  const [proxyUrl, setProxyUrl] = useState(g?.proxy_url || '')
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [testLoading, setTestLoading] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)

  // 仅在 groupId 变化（切换编辑目标）时同步表单；依赖原始值而非对象引用，
  // 避免因 context 中 groups 数组引用更新而不断重置用户正在编辑的内容。
  useEffect(() => {
    const current = groups.find((x) => x.id === groupId)
    if (current) {
      setName(current.name)
      setColor(current.color)
      setProxyUrl(current.proxy_url || '')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId])

  const handleSave = async () => {
    if (!g || !name.trim()) return
    try {
      await onUpdate(g.id, name.trim(), color, proxyUrl)
      toast('分组已更新', 'success')
      onClose()
    } catch (err: any) {
      toast(err.message, 'error')
    }
  }

  const handleDelete = async () => {
    if (!g) return
    setDeleting(true)
    try {
      await onDelete(g.id)
      toast('分组已删除', 'success')
      onClose()
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setDeleting(false)
      setShowDeleteConfirm(false)
    }
  }

  const handleTestProxy = async () => {
    if (!proxyUrl.trim()) return
    setTestLoading(true)
    setTestResult(null)
    try {
      const res = await api.testProxy(proxyUrl.trim())
      setTestResult({ success: res.success, message: res.message })
    } catch (err: any) {
      setTestResult({ success: false, message: err.message })
    } finally {
      setTestLoading(false)
    }
  }

  return (
    <>
      <Modal
        open={!!groupId}
        onClose={onClose}
        title="编辑分组"
        footer={
          <>
            <Button variant="danger" onClick={() => setShowDeleteConfirm(true)}>
              删除
            </Button>
            <Button variant="ghost" onClick={onClose}>取消</Button>
            <Button variant="primary" onClick={handleSave}>保存</Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input label="分组名称" value={name} onChange={(e) => setName(e.target.value)} />
          <div>
            <label className="text-xs font-medium text-gh-text-muted block mb-1.5">颜色</label>
            <div className="flex gap-2 flex-wrap">
              {COLORS.map((c) => (
                <button
                  key={c}
                  onClick={() => setColor(c)}
                  className={`w-7 h-7 rounded-full transition-all ${
                    color === c ? 'ring-2 ring-gh-text ring-offset-2 ring-offset-gh-canvas-subtle scale-110' : ''
                  }`}
                  style={{ background: c }}
                />
              ))}
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-gh-text-muted block mb-1.5">代理地址（可选）</label>
            <div className="flex gap-2">
              <div className="flex-1">
                <Input
                  value={proxyUrl}
                  onChange={(e) => { setProxyUrl(e.target.value); setTestResult(null) }}
                  placeholder="例如: 127.0.0.1:7890 或 http://host:port"
                />
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleTestProxy}
                loading={testLoading}
                disabled={!proxyUrl.trim()}
              >
                测试
              </Button>
            </div>
            {testResult && (
              <div className={`mt-1 text-xs ${testResult.success ? 'text-green-400' : 'text-red-400'}`}>
                {testResult.message}
              </div>
            )}
          </div>
        </div>
      </Modal>

      <ConfirmModal
        open={showDeleteConfirm}
        title="删除分组"
        message={`确定删除分组「${g?.name || ''}」吗？此操作不可撤销。`}
        confirmLabel="删除"
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </>
  )
}

// ========== 中间：邮箱卡片列表 ==========
const EmailList: React.FC<{
  groupId: number | null
  selectedEmailId: number | null
  onSelect: (e: UsableEmail) => void
  selectedEmailIds: Set<number>
  poolEmailIds: Set<number>
  onToggleEmailSelect: (emailId: number) => void
  onRefreshAccount: () => void
  onPoolChanged: () => void | Promise<void>
}> = ({ groupId, selectedEmailId, onSelect, selectedEmailIds, poolEmailIds, onToggleEmailSelect, onRefreshAccount, onPoolChanged }) => {
  const { emails, groups, accounts, refreshEmails, refreshAccounts } = useApp()
  const [showAdd, setShowAdd] = useState(false)
  const [showSettings, setShowSettings] = useState<number | null>(null)
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    let list = emails
    if (groupId !== null) list = list.filter((e) => e.group?.id === groupId)
    if (query) list = list.filter((e) => e.address.toLowerCase().includes(query.toLowerCase()) || (e.label || '').toLowerCase().includes(query.toLowerCase()))
    return list
  }, [emails, groupId, query])

  const group = groups.find((g) => g.id === groupId)

  // Compute latest refresh time across accounts in this filtered view
  const latestRefreshAt = useMemo(() => {
    const accountIds = new Set(filtered.map((e) => e.email_account_id).filter(Boolean) as number[])
    let latest: string | null = null
    for (const a of accounts || []) {
      if (accountIds.has(a.id) && a.last_refresh_at) {
        if (!latest || a.last_refresh_at > latest) latest = a.last_refresh_at
      }
    }
    return latest
  }, [accounts, filtered])

  const refreshTimeLabel = useMemo(() => {
    if (!latestRefreshAt) return ''
    try {
      const d = new Date(latestRefreshAt)
      if (isNaN(d.getTime())) return ''
      const diff = Math.floor((Date.now() - d.getTime()) / 1000)
      if (diff < 60) return '刚刚刷新'
      if (diff < 3600) return `${Math.floor(diff / 60)}分钟前刷新`
      if (diff < 86400) return `${Math.floor(diff / 3600)}小时前刷新`
      return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) + ' 刷新'
    } catch { return '' }
  }, [latestRefreshAt])

  return (
    <div className="w-80 shrink-0 min-h-0 border-r border-gh-border bg-gh-canvas flex flex-col overflow-hidden">
      <div className="px-3 py-2 border-b border-gh-border">
        <div className="flex items-center gap-2">
          <div className="flex-1 flex items-center gap-2 min-w-0">
            {group && (
              <div className="w-2 h-2 rounded-full shrink-0" style={{ background: group.color }} />
            )}
            <span className="text-sm font-semibold text-gh-text truncate">
              {group ? group.name : '全部邮箱'}
            </span>
            <span className="text-xs text-gh-text-secondary tabular-nums">{filtered.length}</span>
          </div>
          <button
            onClick={() => { refreshAccounts(); refreshEmails() }}
            className="p-1.5 rounded-md text-gh-text-muted hover:text-gh-text hover:bg-gh-border/40 transition-colors"
            title="刷新"
          >
            <IconRefresh size={14} />
          </button>
          <button
            onClick={() => setShowAdd(true)}
            className="p-1.5 rounded-md text-gh-text-muted hover:text-gh-accent hover:bg-gh-accent/10 transition-colors"
            title="添加邮箱"
          >
            <IconPlus size={14} />
          </button>
        </div>
        {refreshTimeLabel && (
          <div className="mt-1 text-[10px] text-gh-text-secondary flex items-center gap-1">
            <IconClock size={10} />
            {refreshTimeLabel}
          </div>
        )}
      </div>

      <div className="px-3 py-2 border-b border-gh-border">
        <div className="relative">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索邮箱..."
            className="w-full bg-gh-canvas-inset border border-gh-border rounded-md pl-8 pr-3 py-1.5 text-sm text-gh-text placeholder-gh-text-secondary focus:outline-none focus:border-gh-accent"
          />
          <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gh-text-secondary" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        <AnimatePresence>
          {filtered.map((e) => (
            <EmailCard
              key={e.id}
              email={e}
              selected={selectedEmailId === e.id}
              onClick={() => onSelect(e)}
              onSettings={() => setShowSettings(e.id)}
              selectedForBulk={selectedEmailIds.has(e.id)}
              onToggleBulkSelect={() => onToggleEmailSelect(e.id)}
              onRefreshAccount={onRefreshAccount}
            />
          ))}
        </AnimatePresence>
        {filtered.length === 0 && (
          <div className="text-center py-12 text-sm text-gh-text-secondary">
            暂无邮箱
            <div className="mt-2">
              <Button variant="ghost" size="sm" onClick={() => setShowAdd(true)}>
                <IconPlus size={12} /> 添加
              </Button>
            </div>
          </div>
        )}
      </div>

      <AddEmailModal
        open={showAdd}
        onClose={() => setShowAdd(false)}
        defaultGroupId={groupId}
        onPoolChanged={onPoolChanged}
      />
      <EmailSettingsModal
        emailId={showSettings}
        onClose={() => setShowSettings(null)}
        onPoolChanged={onPoolChanged}
      />
    </div>
  )
}

const EmailCard: React.FC<{
  email: UsableEmail
  selected: boolean
  onClick: () => void
  onSettings: () => void
  selectedForBulk?: boolean
  onToggleBulkSelect?: () => void
  onRefreshAccount?: () => void
}> = ({ email, selected, onClick, onSettings, selectedForBulk, onToggleBulkSelect, onRefreshAccount }) => {
  const { toast } = useToast()
  const { accounts, refreshAccounts, refreshEmails } = useApp()
  const [copied, setCopied] = useState(false)

  const account = (accounts || []).find((a) => a.id === email.email_account_id)
  const refreshTimeLabel = account?.last_refresh_at
    ? formatRelativeTime(account.last_refresh_at)
    : ''
  const [loadingCode, setLoadingCode] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const lastCodeFetchRef = React.useRef<{ time: number; codes: Set<string> }>({ time: 0, codes: new Set() })

  // 三种操作的确认弹窗状态
  type ActionMode = 'activate' | 'deactivate' | 'delete' | null
  const [actionMode, setActionMode] = useState<ActionMode>(null)
  const [actionLoading, setActionLoading] = useState(false)

  const isInactive = email.status === 'inactive'
  const hasAccount = !!email.email_account_id

  const handleRefresh = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!hasAccount) return
    setRefreshing(true)
    try {
      const res = await api.refreshAccount(email.email_account_id!)
      toast(`刷新完成: ${res.email} - ${res.status}`, res.status === 'success' ? 'success' : 'error')
      onRefreshAccount?.()
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setRefreshing(false)
    }
  }

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation()
    navigator.clipboard.writeText(email.address)
    setCopied(true)
    toast('已复制邮箱地址', 'success')
    setTimeout(() => setCopied(false), 1500)
  }

  const handleGetCode = async (e: React.MouseEvent) => {
    e.stopPropagation()
    setLoadingCode(true)
    try {
      const res = await api.readVerification(email.id)
      const now = Date.now()
      const prev = lastCodeFetchRef.current
      const isReFetch = prev.time > 0
      const secondsSinceLast = isReFetch ? (now - prev.time) / 1000 : 0

      if (isReFetch && secondsSinceLast > 30) {
        // User is probably waiting for a NEW verification email — find fresh codes
        const freshMatches = res.matches.filter((m: any) => m.code && !prev.codes.has(m.code))
        if (freshMatches.length > 0) {
          const code = freshMatches[0].code || ''
          navigator.clipboard.writeText(code)
          toast(`新验证码 ${code} 已复制 (距上次 ${Math.floor(secondsSinceLast)}秒)`, 'success')
          // Update seen codes
          freshMatches.forEach((m: any) => prev.codes.add(m.code))
          lastCodeFetchRef.current = { time: now, codes: prev.codes }
        } else {
          // No new codes — fall back to first available
          const match = res.matches[0]
          if (match?.code) {
            navigator.clipboard.writeText(match.code)
            toast(`验证码 ${match.code} 已复制 (暂无新验证码)`, 'info')
          } else {
            toast('未找到验证码 (可能邮件尚未到达)', 'info')
          }
          lastCodeFetchRef.current = { time: now, codes: prev.codes }
        }
      } else {
        // First fetch or quick re-fetch (<30s): return first available code
        const match = res.matches[0]
        if (match?.code) {
          navigator.clipboard.writeText(match.code)
          toast(`验证码 ${match.code} 已复制`, 'success')
          // Track this code
          prev.codes.add(match.code)
          lastCodeFetchRef.current = { time: now, codes: prev.codes }
        } else {
          toast('未找到验证码', 'info')
          lastCodeFetchRef.current = { time: now, codes: prev.codes }
        }
      }
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setLoadingCode(false)
    }
  }

  // ===== 启用 =====
  const handleActivate = async () => {
    setActionLoading(true)
    try {
      if (hasAccount) {
        await api.updateEmailAccount(email.email_account_id!, { status: 'active' })
      } else {
        await api.activateUsableEmail(email.id)
      }
      toast(`「${email.address}」已启用`, 'success')
      refreshAccounts()
      refreshEmails()
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setActionLoading(false)
      setActionMode(null)
    }
  }

  // ===== 停用（软删除，保留数据） =====
  const handleDeactivate = async () => {
    setActionLoading(true)
    try {
      if (hasAccount) {
        await api.deactivateEmailAccount(email.email_account_id!)
      } else {
        await api.deactivateUsableEmail(email.id)
      }
      toast(`「${email.address}」已停用（数据保留）`, 'success')
      refreshAccounts()
      refreshEmails()
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setActionLoading(false)
      setActionMode(null)
    }
  }

  // ===== 删除（硬删除，清空所有关联数据） =====
  const handleDelete = async () => {
    setActionLoading(true)
    try {
      if (hasAccount) {
        await api.deleteEmailAccount(email.email_account_id!)
        toast(`「${email.address}」已彻底删除（含关联别名、绑定、日志等）`, 'success')
      } else {
        await api.deleteUsableEmail(email.id)
        toast(`「${email.address}」已彻底删除`, 'success')
      }
      refreshAccounts()
      refreshEmails()
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setActionLoading(false)
      setActionMode(null)
    }
  }

  return (
    <motion.div layout initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      <Card selected={selected} onClick={onClick} className={`p-3 ${isInactive ? 'opacity-60' : ''}`}>
        <div className="flex items-start gap-2">
          {onToggleBulkSelect ? (
            <div className="shrink-0 pt-1" onClick={(e) => e.stopPropagation()}>
              <input
                type="checkbox"
                checked={!!selectedForBulk}
                onChange={onToggleBulkSelect}
                title="选择此邮箱用于批量操作"
                className="w-3.5 h-3.5 rounded border-gh-border bg-gh-canvas-inset text-gh-accent focus:ring-gh-accent/30 cursor-pointer"
              />
            </div>
          ) : null}
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center text-sm font-semibold shrink-0"
            style={{
              background: (email.group?.color || '#58a6ff') + '20',
              color: email.group?.color || '#58a6ff'
            }}
          >
            {email.address.slice(0, 1).toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 mb-0.5">
              {email.label && (
                <span className="text-xs text-gh-text-secondary truncate">{email.label}</span>
              )}
            </div>
            <button
              onClick={handleCopy}
              className="text-sm text-gh-text font-medium truncate max-w-full hover:text-gh-accent transition-colors group inline-flex items-center gap-1"
            >
              {email.kind === 'primary' && (
                <span className="text-[11px] text-gh-accent shrink-0">主</span>
              )}
              <span className="truncate">{email.address}</span>
              {copied ? (
                <IconCheck size={12} className="shrink-0 text-gh-success" />
              ) : (
                <IconCopy size={12} className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
              )}
            </button>
          </div>
        </div>

        {email.tags && email.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {email.tags.map((t) => (
              <Badge key={t.id} color={t.color}>{t.name}</Badge>
            ))}
          </div>
        )}

        <div className="flex items-center justify-between mt-3 pt-2 border-t border-gh-border/60">
          <span className="text-[11px] text-gh-text-secondary flex items-center gap-1">
            <IconClock size={10} /> {refreshTimeLabel || '—'}
          </span>
          <div className="flex items-center gap-0.5" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={handleGetCode}
              disabled={loadingCode}
              className="p-1 rounded-md text-gh-text-muted hover:text-gh-accent hover:bg-gh-accent/10 transition-colors disabled:opacity-50"
              title="获取验证码"
            >
              {loadingCode ? (
                <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
                  <path d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" fill="currentColor" />
                </svg>
              ) : (
                <IconCode size={13} />
              )}
            </button>
            {hasAccount && onRefreshAccount ? (
              <button
                onClick={handleRefresh}
                disabled={refreshing}
                className="p-1 rounded-md text-gh-text-muted hover:text-gh-accent hover:bg-gh-accent/10 transition-colors disabled:opacity-50"
                title="刷新 Token"
              >
                {refreshing ? (
                  <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
                    <path d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" fill="currentColor" />
                  </svg>
                ) : (
                  <IconRefresh size={13} />
                )}
              </button>
            ) : null}
            <button
              onClick={onSettings}
              className="p-1 rounded-md text-gh-text-muted hover:text-gh-text hover:bg-gh-border/50 transition-colors"
              title="设置"
            >
              <IconSettings size={13} />
            </button>
            {/* 根据状态显示不同操作按钮 */}
            {isInactive ? (
              <button
                onClick={(e) => { e.stopPropagation(); setActionMode('activate') }}
                className="p-1 rounded-md text-gh-text-muted hover:text-green-400 hover:bg-green-400/10 transition-colors"
                title="启用 — 恢复为活跃状态"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </button>
            ) : (
              <>
                <button
                  onClick={(e) => { e.stopPropagation(); setActionMode('deactivate') }}
                  className="p-1 rounded-md text-gh-text-muted hover:text-gh-warning hover:bg-gh-warning/10 transition-colors"
                  title="停用 — 保留数据，可重新启用"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" /><line x1="8" y1="12" x2="16" y2="12" />
                  </svg>
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); setActionMode('delete') }}
                  className="p-1 rounded-md text-gh-text-muted hover:text-red-400 hover:bg-red-400/10 transition-colors"
                  title="删除 — 彻底清除所有关联数据，不可恢复"
                >
                  <IconTrash size={13} />
                </button>
              </>
            )}
          </div>
        </div>
      </Card>

      {/* 启用确认 */}
      <ConfirmModal
        open={actionMode === 'activate'}
        title="启用邮箱"
        message={`确定启用邮箱「${email.address}」吗？将恢复为活跃状态。`}
        confirmLabel="启用"
        danger={false}
        loading={actionLoading}
        onConfirm={handleActivate}
        onCancel={() => setActionMode(null)}
      />

      {/* 停用确认 */}
      <ConfirmModal
        open={actionMode === 'deactivate'}
        title="停用邮箱"
        message={`确定停用邮箱「${email.address}」吗？\n\n数据将保留在数据库中，可随时重新启用。关联别名、绑定等不会丢失。`}
        confirmLabel="停用"
        danger={true}
        loading={actionLoading}
        onConfirm={handleDeactivate}
        onCancel={() => setActionMode(null)}
      />

      {/* 删除确认 — 强调不可逆 */}
      <ConfirmModal
        open={actionMode === 'delete'}
        title="彻底删除邮箱"
        message={`确定要彻底删除「${email.address}」吗？\n\n⚠️ 此操作不可撤销！将强制删除以下所有关联数据：\n• 邮箱账户及所有别名\n• 平台绑定记录\n• 邮箱池条目\n• 验证码读取记录\n• 刷新日志\n• 标签关联`}
        confirmLabel="彻底删除"
        danger={true}
        loading={actionLoading}
        onConfirm={handleDelete}
        onCancel={() => setActionMode(null)}
      />
    </motion.div>
  )
}

// ========== 右侧：邮件详情 ==========
const EmailDetail: React.FC<{ email: UsableEmail | null }> = ({ email }) => {
  const { accounts } = useApp()
  const { toast } = useToast()
  const [messages, setMessages] = React.useState<any[]>([])
  const [codes, setCodes] = React.useState<any[]>([])
  const [links, setLinks] = React.useState<any[]>([])
  const [bindings, setBindings] = React.useState<any[]>([])
  const [loading, setLoading] = React.useState(false)
  const [syncing, setSyncing] = React.useState(false)  // subtle indicator for background fetch
  const [lastRefreshed, setLastRefreshed] = React.useState<Date | null>(null)
  const [elapsed, setElapsed] = React.useState('')
  const [tab, setTab] = React.useState<'messages' | 'verify' | 'bindings'>('messages')
  const [fetching, setFetching] = React.useState(false)
  const [fetchResult, setFetchResult] = React.useState<string | null>(null)
  // Guard against race conditions when rapidly switching emails
  const activeLoadIdRef = React.useRef<number | null>(null)

  const account = (accounts || []).find((a) => a.id === email?.email_account_id)
  const aliases = account?.usable_emails.filter((u) => u.kind === 'alias') || []
  const hasIMAP = !!email?.email_account_id

  const loadData = React.useCallback(async (showSpinner = true) => {
    if (!email) return
    const emailId: number = email.id
    activeLoadIdRef.current = emailId
    if (showSpinner) setLoading(true)
    else setSyncing(true)
    try {
      if (email.kind === 'temp') {
        const [m, c, l] = await Promise.all([
          api.tempMessages(email.id),
          api.tempCodes(email.id),
          api.tempLinks(email.id)
        ])
        if (activeLoadIdRef.current !== emailId) return
        setMessages(m)
        setCodes(c)
        setLinks(l)
      } else if (hasIMAP) {
        // Cache-first: load stored messages first, verification from history
        const [storedMsgs, verifyRes] = await Promise.all([
          api.getMessages(email.id).catch(() => []),
          api.readVerification(email.id).catch(() => ({ matches: [] }))
        ])
        if (activeLoadIdRef.current !== emailId) return
        setMessages(storedMsgs.map((m: any) => ({
          id: m.id,
          from_address: m.from_address || '—',
          subject: m.subject || '(无主题)',
          text: m.body || '',
          received_at: m.received_at || m.created_at || ''
        })))
        setCodes(verifyRes.matches.filter((x: any) => x.code).map((x: any, i: number) => ({
          message_id: `v_${i}`,
          code: x.code
        })))
        setLinks(verifyRes.matches.filter((x: any) => x.link).map((x: any, i: number) => ({
          message_id: `v_${i}`,
          url: x.link
        })))
      } else {
        if (activeLoadIdRef.current !== emailId) return
        setMessages([])
        setCodes([])
        setLinks([])
      }
      const b = await api.listBindings(email.id)
      if (activeLoadIdRef.current !== emailId) return
      setBindings(b)
      setLastRefreshed(new Date())
    } catch (err: any) {
      if (activeLoadIdRef.current !== emailId) return
      console.error(err)
      toast(err?.message || '加载失败', 'error')
    } finally {
      if (activeLoadIdRef.current === emailId) {
        setLoading(false)
        setSyncing(false)
      }
    }
  }, [email, toast, hasIMAP])

  // 手动触发 IMAP 拉取
  const handleFetchEmails = async () => {
    if (!email || !hasIMAP) return
    const emailId: number = email.id
    activeLoadIdRef.current = emailId
    setFetching(true)
    setFetchResult(null)
    setSyncing(true)
    try {
      const res = await api.fetchEmails(email.id)
      if (activeLoadIdRef.current !== emailId) return
      const error = res.error || ''
      if (error) {
        toast(`拉取失败: ${error}`, 'error')
        setFetchResult(`❌ ${error}`)
      } else if (res.messages_stored === 0) {
        setFetchResult('已是最新')
      } else {
        toast(`拉取完成: ${res.messages_stored} 封新邮件, ${res.codes_found} 个验证码`, 'success')
        setFetchResult(`${res.messages_stored} 封新邮件, ${res.codes_found} 个验证码`)
        // Reload data without spinner to merge new messages into display
        setTimeout(() => loadData(false), 300)
      }
    } catch (err: any) {
      if (activeLoadIdRef.current !== emailId) return
      toast(`网络错误: ${err.message}`, 'error')
      setFetchResult(`❌ ${err.message}`)
    } finally {
      if (activeLoadIdRef.current === emailId) {
        setFetching(false)
        setSyncing(false)
      }
    }
  }

  const fetchTriggeredRef = React.useRef<number | null>(null)

  useEffect(() => {
    if (!email) return
    // Clear previous email's data immediately to avoid showing stale content
    setMessages([])
    setCodes([])
    setLinks([])
    setBindings([])
    setFetchResult(null)
    // Cache-first: load immediately with spinner (first load), then background sync
    loadData(true)
    // Auto-trigger IMAP fetch to get latest emails (each email only once per selection)
    if (hasIMAP && fetchTriggeredRef.current !== email.id) {
      fetchTriggeredRef.current = email.id
      setTimeout(() => handleFetchEmails(), 300)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [email])

  // 更新 "X 秒前" 显示
  useEffect(() => {
    if (!lastRefreshed) { setElapsed(''); return }
    const update = () => {
      const diff = Math.floor((Date.now() - lastRefreshed.getTime()) / 1000)
      if (diff < 5) setElapsed('刚刚')
      else if (diff < 60) setElapsed(`${diff}秒前`)
      else if (diff < 3600) setElapsed(`${Math.floor(diff / 60)}分钟前`)
      else setElapsed(`${Math.floor(diff / 3600)}小时前`)
    }
    update()
    const timer = setInterval(update, 10000)
    return () => clearInterval(timer)
  }, [lastRefreshed])

  if (!email) {
    return (
      <div className="flex-1 flex items-center justify-center text-gh-text-secondary text-sm">
        <div className="text-center">
          <IconMail size={48} className="mx-auto mb-3 opacity-30" />
          <div>选择一个邮箱查看详情</div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
      {/* 头部信息 */}
      <motion.div
        key={email.id}
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="px-6 py-4 border-b border-gh-border bg-gradient-to-r from-gh-canvas-subtle to-gh-canvas"
      >
        <div className="flex items-start gap-3">
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center text-lg font-bold shrink-0"
            style={{
              background: (email.group?.color || '#58a6ff') + '20',
              color: email.group?.color || '#58a6ff'
            }}
          >
            {email.address.slice(0, 1).toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-lg font-semibold text-gh-text truncate">
                {email.label || email.address}
              </h2>
              <Badge color={
                email.kind === 'primary' ? '#58a6ff' :
                email.kind === 'alias' ? '#a371f7' :
                email.kind === 'temp' ? '#f0883e' : '#6e7681'
              }>
                {email.kind === 'primary' ? '主邮箱' : email.kind === 'alias' ? '别名' : email.kind === 'temp' ? '临时' : '自定义'}
              </Badge>
              {email.status === 'active' ? (
                <Badge color="#3fb950">活跃</Badge>
              ) : (
                <Badge color="#6e7681">{email.status}</Badge>
              )}
            </div>
            <div className="text-sm text-gh-text-muted font-mono mt-0.5">{email.address}</div>
            {email.group && (
              <div className="flex items-center gap-1 mt-1 text-xs text-gh-text-secondary">
                <div className="w-2 h-2 rounded-sm" style={{ background: email.group.color }} />
                {email.group.name}
              </div>
            )}
          </div>
        </div>

        {account && (
          <div className="mt-3 pt-3 border-t border-gh-border/60 flex items-center gap-2 text-xs text-gh-text-secondary flex-wrap">
            <IconUser size={12} />
            <span>关联账户：<span className="text-gh-text">{account.display_name}</span></span>
            <span>·</span>
            <span>{account.provider}</span>
            {aliases.length > 0 && (
              <>
                <span>·</span>
                <span>{aliases.length} 个别名</span>
              </>
            )}
            <div className="flex-1" />
            {elapsed && (
              <span className="text-[11px] text-gh-text-secondary whitespace-nowrap">
                <IconClock size={10} className="inline mr-1" />
                {elapsed}
              </span>
            )}
            {fetchResult && (
              <span className="text-xs text-gh-text-muted">{fetchResult}</span>
            )}
          </div>
        )}

        {/* 别名列表 */}
        {aliases.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {aliases.map((a) => (
              <div
                key={a.id}
                className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-gh-canvas-inset border border-gh-border text-xs text-gh-text-muted"
              >
                <IconAt size={10} />
                <span className="font-mono">{a.address}</span>
              </div>
            ))}
          </div>
        )}
      </motion.div>

      {/* Tabs */}
      <div className="sticky top-0 z-10 flex items-center gap-1 px-6 border-b border-gh-border bg-gh-canvas-subtle/40 backdrop-blur-sm">
        {[
          { k: 'messages', label: '邮件', icon: IconMail, count: messages.length },
          { k: 'verify', label: '验证码/链接', icon: IconKey, count: codes.length + links.length },
          { k: 'bindings', label: '平台绑定', icon: IconLink, count: bindings.length }
        ].map((t) => (
          <button
            key={t.k}
            onClick={() => setTab(t.k as any)}
            className={`px-3 py-2.5 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
              tab === t.k
                ? 'border-gh-accent text-gh-accent'
                : 'border-transparent text-gh-text-muted hover:text-gh-text'
            }`}
          >
            <t.icon size={13} />
            {t.label}
            {t.count > 0 && (
              <span className="ml-1 px-1.5 py-0 text-[10px] rounded-full bg-gh-border/50 tabular-nums">
                {t.count}
              </span>
            )}
          </button>
        ))}
        {/* 刷新按钮 */}
        <div className="flex-1" />
        <div className="flex items-center gap-2 pr-2">
          <button
            onClick={() => { if (hasIMAP) handleFetchEmails(); else loadData() }}
            disabled={loading || fetching}
            className="px-2 py-1 rounded text-xs text-gh-accent bg-gh-accent/10 border border-gh-accent/20 hover:bg-gh-accent/20 transition-colors disabled:opacity-50 flex items-center gap-1"
            title={hasIMAP ? '从 IMAP 拉取最新邮件并存入数据库' : '刷新视图'}
          >
            {loading || fetching ? (
              <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
                <path d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" fill="currentColor" />
              </svg>
            ) : (
              <IconRefresh size={12} />
            )}
            {hasIMAP ? '拉取' : '刷新'}
          </button>
        </div>
      </div>

      {/* Content */}
      {/* Custom scrollbar styles */}
      <style>{`
        .email-detail-scroll::-webkit-scrollbar { width: 6px; height: 6px; }
        .email-detail-scroll::-webkit-scrollbar-track { background: transparent; }
        .email-detail-scroll::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
        .email-detail-scroll::-webkit-scrollbar-thumb:hover { background: #484f58; }
        .email-detail-scroll::-webkit-scrollbar-corner { background: transparent; }
        /* Firefox */
        .email-detail-scroll { scrollbar-width: thin; scrollbar-color: #30363d transparent; }
      `}</style>
      <div className="flex-1 overflow-y-auto p-6 email-detail-scroll">
        {/* Subtle syncing indicator */}
        {syncing && (
          <div className="mb-3 flex items-center gap-2 text-xs text-gh-accent/70">
            <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
              <path d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" fill="currentColor" />
            </svg>
            正在同步最新邮件…
          </div>
        )}
        <AnimatePresence mode="wait">
          {loading && messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-gh-text-secondary">
              <svg className="animate-spin h-8 w-8 mb-3 text-gh-accent" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
                <path d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" fill="currentColor" />
              </svg>
              <span className="text-sm">正在加载邮件数据…</span>
            </div>
          ) : tab === 'messages' ? (
            <MessagesTab messages={messages} />
          ) : tab === 'verify' ? (
            <VerifyTab codes={codes} links={links} />
          ) : (
            <BindingsTab bindings={bindings} emailId={email.id} />
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

const MessagesTab: React.FC<{ messages: any[] }> = ({ messages }) => {
  const [expandedId, setExpandedId] = React.useState<string | number | null>(null)
  const [darkMode, setDarkMode] = React.useState(true)
  if (messages.length === 0) {
    return <div className="text-center py-12 text-gh-text-secondary text-sm">暂无邮件</div>
  }
  return (
    <>
      {/* Dark-mode override for email HTML bodies */}
      {darkMode && (
        <style>{`
        .email-body-dark, .email-body-dark * { color-scheme: dark !important; }
        .email-body-dark { color: #c9d1d9 !important; background-color: #0d1117 !important; }
        .email-body-dark a, .email-body-dark a:link, .email-body-dark a:visited { color: #58a6ff !important; }
        .email-body-dark table, .email-body-dark td, .email-body-dark th, .email-body-dark tr,
        .email-body-dark tbody, .email-body-dark thead, .email-body-dark div, .email-body-dark p,
        .email-body-dark span, .email-body-dark h1, .email-body-dark h2, .email-body-dark h3,
        .email-body-dark h4, .email-body-dark h5, .email-body-dark h6, .email-body-dark li,
        .email-body-dark dl, .email-body-dark dt, .email-body-dark dd, .email-body-dark section,
        .email-body-dark article, .email-body-dark header, .email-body-dark footer {
          background-color: transparent !important; color: #c9d1d9 !important; border-color: #30363d !important;
        }
        .email-body-dark img { filter: brightness(0.85) contrast(0.9) !important; }
        .email-body-dark hr { border-color: #30363d !important; }
        .email-body-dark blockquote { border-left-color: #30363d !important; color: #8b949e !important; }
        .email-body-dark code, .email-body-dark pre { background-color: #161b22 !important; color: #c9d1d9 !important; border-color: #30363d !important; }
        .email-body-dark input, .email-body-dark textarea, .email-body-dark button, .email-body-dark select { background-color: #161b22 !important; color: #c9d1d9 !important; border-color: #30363d !important; }
      `}</style>
      )}
    <div className="space-y-1.5">
      {/* Dark mode toggle */}
      <div className="flex items-center justify-end mb-1">
        <button
          onClick={() => setDarkMode(!darkMode)}
          className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors ${
            darkMode
              ? 'bg-gh-accent/10 text-gh-accent border border-gh-accent/20'
              : 'bg-gh-canvas-inset text-gh-text-muted border border-gh-border hover:text-gh-text'
          }`}
          title={darkMode ? '关闭邮件暗色模式' : '开启邮件暗色模式'}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            {darkMode ? (
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            ) : (
              <>
                <circle cx="12" cy="12" r="5" />
                <line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" />
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                <line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" />
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
              </>
            )}
          </svg>
          暗色模式
        </button>
      </div>
      {messages.map((m, i) => {
        const isExpanded = expandedId === m.id
        const avatarColor = stringToColor(m.from_address || m.subject || '?')
        const timeLabel = formatRelativeTime(m.received_at || m.created_at)
        return (
          <motion.div
            key={m.id}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.02 }}
            onClick={() => setExpandedId(isExpanded ? null : m.id)}
            className={`rounded-lg border transition-all cursor-pointer ${
              isExpanded
                ? 'border-gh-accent/40 bg-gh-canvas shadow-sm'
                : 'border-gh-border/60 bg-gh-canvas-subtle hover:border-gh-text-muted hover:bg-gh-canvas'
            }`}
          >
            {/* Compact card header — always visible */}
            <div className="flex items-center gap-3 px-3 py-2.5">
              <div
                className="w-9 h-9 rounded-lg flex items-center justify-center text-xs font-bold shrink-0"
                style={{ background: avatarColor + '20', color: avatarColor }}
              >
                {(m.from_address || '?').slice(0, 1).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <div className={`font-medium truncate ${isExpanded ? 'text-gh-accent' : 'text-gh-text'}`}>
                    {m.subject || '(无主题)'}
                  </div>
                  {timeLabel && (
                    <span className="text-[10px] text-gh-text-secondary whitespace-nowrap shrink-0">
                      {timeLabel}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-xs text-gh-text-muted truncate">{m.from_address || '—'}</span>
                  {m.text && !isExpanded && (
                    <span className="text-xs text-gh-text-secondary truncate hidden sm:inline">
                      — {m.text.slice(0, 60)}{m.text.length > 60 ? '...' : ''}
                    </span>
                  )}
                </div>
              </div>
              <svg
                className={`w-4 h-4 text-gh-text-muted shrink-0 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </div>
            {/* Expanded body */}
            <AnimatePresence>
              {isExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <div
                    className="px-3 pb-3 pt-0 border-t border-gh-border/40 mx-3"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="mt-3 text-sm text-gh-text leading-relaxed break-words font-sans bg-gh-canvas-inset rounded-lg p-3 max-h-96 overflow-y-auto">
                      {m.html ? (
                        <div
                          className={darkMode ? 'email-body-dark' : ''}
                          style={EMAIL_BODY_STYLE}
                          dangerouslySetInnerHTML={{ __html: sanitizeHtml(m.html) }}
                        />
                      ) : looksLikeHtml(m.text) ? (
                        <div
                          className={darkMode ? 'email-body-dark' : ''}
                          style={EMAIL_BODY_STYLE}
                          dangerouslySetInnerHTML={{ __html: sanitizeHtml(m.text) }}
                        />
                      ) : (
                        <div className="whitespace-pre-wrap">{m.text || '(无正文)'}</div>
                      )}
                    </div>
                    {m.received_at && (
                      <div className="mt-2 text-[11px] text-gh-text-secondary flex items-center gap-1">
                        <IconClock size={10} />
                        收到时间: {m.received_at}
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        )
      })}
    </div>
    </>
  )
}

/** Deterministic color from string for avatar backgrounds */
function stringToColor(s: string): string {
  const colors = ['#58a6ff', '#a371f7', '#f0883e', '#3fb950', '#f85149', '#d29922', '#79c0ff', '#bc8cff']
  let hash = 0
  for (let i = 0; i < s.length; i++) hash = ((hash << 5) - hash + s.charCodeAt(i)) | 0
  return colors[Math.abs(hash) % colors.length]
}

/** Format ISO timestamps as relative time strings */
function formatRelativeTime(iso: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    const now = Date.now()
    const diff = Math.floor((now - d.getTime()) / 1000)
    if (diff < 60) return '刚刚'
    if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
    if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
    if (diff < 604800) return `${Math.floor(diff / 86400)}天前`
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch { return iso }
}

/** Detect if text content looks like HTML */
function looksLikeHtml(text: string | undefined): boolean {
  if (!text) return false
  return /<\s*(html|body|div|table|p|a|img|br|span|style|head)\b/i.test(text)
}

/** Basic HTML sanitizer: strip script/style tags, keep structural tags */
function sanitizeHtml(raw: string): string {
  return raw
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, '')
    .replace(/\bon\w+\s*=\s*"[^"]*"/gi, '')
    .replace(/\bon\w+\s*=\s*'[^']*'/gi, '')
}

function normalizePoolEntries(response: any): any[] {
  if (Array.isArray(response)) return response
  if (Array.isArray(response?.entries)) return response.entries
  return []
}

function getPoolEntryUsableEmailId(entry: any): number | null {
  const raw = entry?.usable_email?.id ?? entry?.usable_email_id
  const id = typeof raw === 'number' ? raw : Number(raw)
  return Number.isFinite(id) ? id : null
}

function getPoolEmailIdSet(response: any): Set<number> {
  const ids = normalizePoolEntries(response)
    .map(getPoolEntryUsableEmailId)
    .filter((id): id is number => id !== null)
  return new Set(ids)
}

const VerifyTab: React.FC<{ codes: any[]; links: any[] }> = ({ codes, links }) => {
  const { toast } = useToast()
  if (codes.length === 0 && links.length === 0) {
    return <div className="text-center py-12 text-gh-text-secondary text-sm">暂无验证码或链接</div>
  }
  return (
    <div className="space-y-4">
      {codes.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-gh-text-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <IconKey size={12} /> 验证码 ({codes.length})
          </h4>
          <div className="grid grid-cols-2 gap-2">
            {codes.map((c) => (
              <button
                key={c.message_id}
                onClick={() => {
                  navigator.clipboard.writeText(c.code)
                  toast('验证码已复制', 'success')
                }}
                className="px-3 py-2.5 rounded-lg border border-gh-border bg-gh-canvas-subtle hover:border-gh-accent hover:bg-gh-accent/5 transition-colors text-left"
              >
                <div className="text-xs text-gh-text-secondary mb-0.5">CODE</div>
                <div className="text-lg font-mono font-bold text-gh-accent tracking-wider">
                  {c.code}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
      {links.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-gh-text-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <IconLink size={12} /> 验证链接 ({links.length})
          </h4>
          <div className="space-y-2">
            {links.map((l) => (
              <a
                key={l.message_id}
                href={l.url}
                target="_blank"
                rel="noreferrer"
                className="block px-3 py-2 rounded-lg border border-gh-border bg-gh-canvas-subtle hover:border-gh-accent hover:bg-gh-accent/5 transition-colors"
              >
                <div className="text-xs text-gh-text-secondary mb-0.5">LINK</div>
                <div className="text-xs font-mono text-gh-accent truncate">{l.url}</div>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const BindingsTab: React.FC<{ bindings: any[]; emailId: number }> = ({ bindings, emailId }) => {
  const { platforms, refreshEmails } = useApp()
  const { toast } = useToast()
  const [showBind, setShowBind] = useState(false)
  const [selPlatform, setSelPlatform] = useState<number | ''>('')

  const handleBind = async () => {
    if (!selPlatform) return
    try {
      await api.createBinding(emailId, selPlatform as number)
      toast('已绑定平台', 'success')
      setShowBind(false)
      setSelPlatform('')
      refreshEmails()
    } catch (err: any) {
      toast(err.message, 'error')
    }
  }

  const statusColors: Record<string, string> = {
    active: '#3fb950',
    pending_verification: '#d29922',
    risk: '#f85149',
    disabled: '#6e7681',
    archived: '#6e7681'
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-gh-text">平台绑定</h4>
        <Button size="sm" variant="secondary" onClick={() => setShowBind(true)}>
          <IconPlus size={12} /> 绑定平台
        </Button>
      </div>

      {bindings.length === 0 ? (
        <div className="text-center py-12 text-gh-text-secondary text-sm">
          暂无绑定
          <div className="mt-2">
            <Button size="sm" variant="ghost" onClick={() => setShowBind(true)}>
              <IconPlus size={12} /> 绑定第一个平台
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          {bindings.map((b) => (
            <div
              key={b.id}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-gh-border bg-gh-canvas-subtle"
            >
              <div className="w-8 h-8 rounded-md bg-gh-accent/10 text-gh-accent flex items-center justify-center">
                <IconShield size={14} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-gh-text">{b.platform.name}</div>
                {b.notes && <div className="text-xs text-gh-text-secondary truncate">{b.notes}</div>}
              </div>
              <Badge color={statusColors[b.status]}>
                {b.status === 'active' ? '活跃' : b.status === 'pending_verification' ? '待验证' : b.status}
              </Badge>
            </div>
          ))}
        </div>
      )}

      <Modal
        open={showBind}
        onClose={() => setShowBind(false)}
        title="绑定平台"
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowBind(false)}>取消</Button>
            <Button variant="primary" onClick={handleBind} disabled={!selPlatform}>绑定</Button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-gh-text-muted block mb-1.5">选择平台</label>
            <select
              value={selPlatform}
              onChange={(e) => setSelPlatform(Number(e.target.value))}
              className="w-full bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-1.5 text-sm text-gh-text focus:outline-none focus:border-gh-accent"
            >
              <option value="">请选择...</option>
              {platforms.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
        </div>
      </Modal>
    </div>
  )
}

// ========== 凭证导入 Modal ==========
const AddEmailModal: React.FC<{
  open: boolean
  onClose: () => void
  defaultGroupId: number | null
  onPoolChanged?: () => void | Promise<void>
}> = ({ open, onClose, defaultGroupId, onPoolChanged }) => {
  const { refreshAccounts, refreshEmails, groups } = useApp()
  const { toast } = useToast()
  const [groupId, setGroupId] = useState<number | ''>('')
  const [provider, setProvider] = useState('outlook')
  const [credentialText, setCredentialText] = useState('')
  const [addToPool, setAddToPool] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AccountImportResult | null>(null)

  useEffect(() => {
    if (open) {
      setGroupId(defaultGroupId ?? '')
      setResult(null)
    }
  }, [open, defaultGroupId])

  const reset = () => {
    setGroupId('')
    setProvider('outlook')
    setCredentialText('')
    setAddToPool(false)
    setResult(null)
  }

  const handleSave = async () => {
    if (!credentialText.trim()) return
    setLoading(true)
    setResult(null)
    try {
      const res = await api.importEmailAccounts(credentialText, {
        provider,
        group_id: groupId || null,
        add_to_pool: addToPool,
      })
      await Promise.all([refreshAccounts(), refreshEmails(), addToPool ? onPoolChanged?.() : Promise.resolve()])
      setResult(res)
      if (res.imported > 0) toast(`成功导入 ${res.imported} 个账户`, 'success')
      if (res.skipped > 0) toast(`跳过 ${res.skipped} 个重复账户`, 'info')
      if (res.failed > 0) toast(`${res.failed} 个账户导入失败`, 'error')
      // 不清空表单，让用户可以查看结果后继续导入或关闭
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  const isOutlook = provider === 'outlook'
  const hasResult = result !== null
  const totalProcessed = (result?.imported ?? 0) + (result?.skipped ?? 0) + (result?.failed ?? 0)

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="凭证导入"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={handleClose}>{hasResult ? '关闭' : '取消'}</Button>
          <Button variant="primary" onClick={handleSave} loading={loading} disabled={loading}>
            {hasResult ? '继续导入' : '导入'}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {/* 导入结果摘要 */}
        {hasResult && (
          <div className="rounded-lg border border-gh-border bg-gh-canvas-inset overflow-hidden">
            <div className="px-4 py-3 border-b border-gh-border bg-gh-canvas-subtle">
              <span className="text-sm font-semibold text-gh-text">导入结果</span>
              <span className="text-xs text-gh-text-secondary ml-2">共处理 {totalProcessed} 个账户</span>
            </div>
            <div className="px-4 py-3">
              <div className="grid grid-cols-3 gap-3 mb-3">
                <div className="text-center p-2 rounded-md bg-gh-success/10 border border-gh-success/20">
                  <div className="text-lg font-bold text-gh-success tabular-nums">{result.imported}</div>
                  <div className="text-[11px] text-gh-text-secondary">成功导入</div>
                </div>
                <div className="text-center p-2 rounded-md bg-gh-warning/10 border border-gh-warning/20">
                  <div className="text-lg font-bold text-gh-warning tabular-nums">{result.skipped}</div>
                  <div className="text-[11px] text-gh-text-secondary">跳过（重复）</div>
                </div>
                <div className="text-center p-2 rounded-md bg-gh-danger/10 border border-gh-danger/20">
                  <div className="text-lg font-bold text-gh-danger tabular-nums">{result.failed}</div>
                  <div className="text-[11px] text-gh-text-secondary">失败</div>
                </div>
              </div>
              {/* 错误详情 */}
              {(result.errors?.length ?? 0) > 0 && (
                <details className="mt-2">
                  <summary className="text-xs text-gh-text-muted cursor-pointer hover:text-gh-text">
                    查看 {result.errors.length} 条错误详情（含 {result.errors_total ?? result.errors.length} 条）
                  </summary>
                  <div className="mt-2 max-h-40 overflow-y-auto space-y-1">
                    {result.errors.map((err, i) => (
                      <div key={i} className="text-xs font-mono px-2 py-1 rounded bg-gh-danger/5 border border-gh-danger/10">
                        <span className="text-gh-text-secondary">#{err.line}</span>
                        {err.email && <span className="text-gh-text-muted ml-2">{err.email}</span>}
                        <span className="text-gh-danger ml-2">{err.error}</span>
                      </div>
                    ))}
                  </div>
                </details>
              )}
              {result.errors_total > (result.errors?.length ?? 0) && (
                <p className="text-xs text-gh-text-secondary mt-1">
                  仅显示前 {result.errors.length} 条，共 {result.errors_total} 条错误
                </p>
              )}
            </div>
          </div>
        )}

        {/* 分组 */}
        <div>
          <label className="text-xs font-medium text-gh-text-muted block mb-1.5">分组</label>
          <select
            value={groupId}
            onChange={(e) => setGroupId(e.target.value ? Number(e.target.value) : '')}
            className="w-full bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-1.5 text-sm text-gh-text focus:outline-none focus:border-gh-accent"
          >
            <option value="">无分组</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>
        </div>

        {/* 服务商 */}
        <div>
          <label className="text-xs font-medium text-gh-text-muted block mb-1.5">服务商</label>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="w-full bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-1.5 text-sm text-gh-text focus:outline-none focus:border-gh-accent"
          >
            <option value="outlook">Outlook</option>
            <option value="gmail">Gmail</option>
            <option value="yahoo">Yahoo</option>
            <option value="icloud">iCloud</option>
            <option value="qq">QQ邮箱</option>
            <option value="163">163邮箱</option>
            <option value="126">126邮箱</option>
            <option value="other">其他</option>
          </select>
        </div>

        {/* 凭证输入 */}
        <div>
          <label className="text-xs font-medium text-gh-text-muted block mb-1.5">
            凭证信息（每行一个账户）
          </label>
          <textarea
            value={credentialText}
            onChange={(e) => setCredentialText(e.target.value)}
            className="w-full min-h-40 bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-2 text-sm text-gh-text font-mono focus:outline-none focus:border-gh-accent"
            placeholder={
              isOutlook
                ? '邮箱----密码----client_id----refresh_token'
                : '邮箱----IMAP授权码/应用密码'
            }
          />
          <p className="text-xs text-gh-text-secondary mt-1.5">
            {isOutlook
              ? 'Outlook 格式：邮箱----密码----client_id----refresh_token'
              : '格式：邮箱----IMAP授权码/应用密码'}
          </p>
        </div>

        {/* 导入到邮箱池 */}
        <label className="flex items-center gap-2 text-sm text-gh-text-secondary cursor-pointer">
          <input
            type="checkbox"
            checked={addToPool}
            onChange={(e) => setAddToPool(e.target.checked)}
            className="w-4 h-4 rounded border-gh-border bg-gh-canvas-inset text-gh-accent focus:ring-gh-accent/30"
          />
          导入到邮箱池
        </label>
      </div>
    </Modal>
  )
}

// ========== 邮箱设置 Modal ==========
const EmailSettingsModal: React.FC<{
  emailId: number | null
  onClose: () => void
  onPoolChanged?: () => void | Promise<void>
}> = ({ emailId, onClose, onPoolChanged }) => {
  const { emails, groups, tags, organizeEmail, addAlias, accounts, refreshAccounts, refreshEmails } = useApp()
  const { toast } = useToast()
  const email = emails.find((e) => e.id === emailId)
  const account = (accounts || []).find((a) => a.id === email?.email_account_id)
  const [activeTab, setActiveTab] = useState<'info' | 'credentials'>('info')
  const [label, setLabel] = useState('')
  const [groupId, setGroupId] = useState<number | ''>('')
  const [tagIds, setTagIds] = useState<number[]>([])
  const [newAlias, setNewAlias] = useState('')
  const [loading, setLoading] = useState(false)
  // Credential fields
  const [credPwd, setCredPwd] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [credCid, setCredCid] = useState('')
  const [credRtk, setCredRtk] = useState('')
  const [credStatus, setCredStatus] = useState('active')
  const [credLoaded, setCredLoaded] = useState(false)
  // Account remark (多行备注)
  const [remark, setRemark] = useState('')
  // 邮箱池
  const [inPool, setInPool] = useState(false)
  const [initialInPool, setInitialInPool] = useState(false)
  const [poolLoaded, setPoolLoaded] = useState(false)
  // 已有别名列表
  const aliases = (account?.usable_emails || []).filter((u) => u.kind === 'alias')

  useEffect(() => {
    if (email) {
      setLabel(email.label || '')
      setGroupId(email.group?.id || '')
      setTagIds(email.tags?.map((t) => t.id) || [])
      setCredLoaded(false)
      setInPool(false)
      setInitialInPool(false)
      setPoolLoaded(false)
      setShowPwd(false)
      setRemark('')
    }
  }, [email])

  // 加载凭证信息
  useEffect(() => {
    if (email?.email_account_id && !credLoaded) {
      api.getEmailAccount(email.email_account_id).then((acc: any) => {
        setCredPwd(acc.imap_password || '')
        setCredCid(acc.client_id || '')
        setCredRtk(acc.refresh_token || '')
        setCredStatus(acc.status || 'active')
        setRemark(acc.remark || '')
        setCredLoaded(true)
      }).catch(() => setCredLoaded(true))
    }
  }, [email?.email_account_id, credLoaded])

  // 加载邮箱池状态
  useEffect(() => {
    if (!email) return
    let cancelled = false
    const emailId = email.id
    setPoolLoaded(false)
    setInPool(false)
    setInitialInPool(false)
    api.listPoolEntries().then((entries: any) => {
      if (cancelled) return
      const currentInPool = getPoolEmailIdSet(entries).has(emailId)
      setInPool(currentInPool)
      setInitialInPool(currentInPool)
    }).catch(() => {
      if (!cancelled) {
        setInPool(false)
        setInitialInPool(false)
      }
    }).finally(() => {
      if (!cancelled) setPoolLoaded(true)
    })
    return () => { cancelled = true }
  }, [email?.id])

  const handleSave = async () => {
    if (!email) return
    setLoading(true)
    try {
      await organizeEmail(email.id, {
        label,
        group_id: groupId || null,
        tag_ids: tagIds
      })
      if (email.email_account_id) {
        await api.updateEmailAccount(email.email_account_id, {
          password: credPwd || null,
          client_id: credCid || null,
          refresh_token: credRtk || null,
          group_id: groupId || null,
          status: credStatus,
          remark: remark || null,
        })
      }
      if (inPool && !initialInPool && email.email_account_id) {
        await api.addPoolEntry(email.id)
        await onPoolChanged?.()
        setInitialInPool(true)
      } else if (!inPool && initialInPool && email.email_account_id) {
        await api.removePoolEntry(email.id)
        await onPoolChanged?.()
        setInitialInPool(false)
      }
      toast('已保存', 'success')
      refreshAccounts()
      refreshEmails()
      onClose()
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleAddAlias = async () => {
    if (!email || !newAlias) return
    const acc = (accounts || []).find((a) => a.id === email.email_account_id)
    if (!acc) {
      toast('该邮箱没有关联的账户', 'error')
      return
    }
    try {
      await addAlias(acc.id, newAlias)
      toast('别名已添加', 'success')
      setNewAlias('')
      refreshAccounts()
      refreshEmails()
    } catch (err: any) {
      toast(err.message, 'error')
    }
  }

  const isOutlook = account?.provider === 'outlook'

  return (
    <Modal
      open={!!emailId}
      onClose={onClose}
      title="邮箱设置"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={handleSave} loading={loading}>保存</Button>
        </>
      }
    >
      {email && (
        <div className="space-y-4">
          {/* Tab bar */}
          <div className="flex border-b border-gh-border -mx-5 -mt-4 px-5">
            <button
              type="button"
              onClick={() => setActiveTab('info')}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'info'
                  ? 'border-gh-accent text-gh-accent'
                  : 'border-transparent text-gh-text-muted hover:text-gh-text'
              }`}
            >
              信息
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('credentials')}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'credentials'
                  ? 'border-gh-accent text-gh-accent'
                  : 'border-transparent text-gh-text-muted hover:text-gh-text'
              }`}
            >
              凭证
            </button>
          </div>

          {activeTab === 'info' && (
            <>
              {/* 邮箱地址（只读展示） */}
              <div className="px-3 py-2 rounded-md bg-gh-canvas-inset border border-gh-border">
                <div className="text-xs text-gh-text-secondary">邮箱地址</div>
                <div className="text-sm font-mono text-gh-text">{email.address}</div>
              </div>

              {/* 备注名称 */}
              <Input label="备注名称" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="例如：主邮箱" />

              {/* 账号备注（多行） */}
              <div>
                <label className="text-xs font-medium text-gh-text-muted block mb-1.5">
                  账号备注
                </label>
                <textarea
                  value={remark}
                  onChange={(e) => setRemark(e.target.value)}
                  placeholder="添加账号备注信息…"
                  rows={3}
                  className="w-full bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-2 text-sm text-gh-text placeholder-gh-text-secondary focus:outline-none focus:border-gh-accent resize-y"
                />
              </div>

              {/* 分组 */}
              <Select
                label="分组"
                value={groupId}
                onChange={(v) => setGroupId(v ? Number(v) : '')}
                options={[
                  { value: '', label: '无分组' },
                  ...groups.map((g) => ({ value: g.id, label: g.name }))
                ]}
              />

              {/* 邮箱池 */}
              {email.email_account_id ? (
                <Checkbox
                  label={inPool ? '已加入邮箱池' : '加入邮箱池'}
                  checked={inPool}
                  onChange={setInPool}
                  disabled={!poolLoaded}
                  title={poolLoaded ? undefined : '正在检测邮箱池状态…'}
                />
              ) : (
                <div className="text-sm text-gh-text-secondary">无关联账户，不能加入邮箱池</div>
              )}

              {/* 别名邮箱 */}
              <div className="pt-3 border-t border-gh-border">
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <label className="text-xs font-medium text-gh-text-muted">
                    别名邮箱
                  </label>
                  {isOutlook && (
                    <a
                      href={OUTLOOK_ALIAS_MANAGE_URL}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-gh-accent hover:underline"
                    >
                      <IconLink size={11} />
                      设置别名邮箱
                    </a>
                  )}
                </div>
                {aliases.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {aliases.map((a) => (
                      <div
                        key={a.id}
                        className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-gh-canvas-inset border border-gh-border text-xs text-gh-text-muted"
                      >
                        <IconAt size={10} />
                        <span className="font-mono">{a.address}</span>
                      </div>
                    ))}
                  </div>
                )}
                <div className="flex gap-2">
                  <Input
                    value={newAlias}
                    onChange={(e) => setNewAlias(e.target.value)}
                    placeholder="alias@domain.com"
                    className="flex-1"
                  />
                  <Button variant="secondary" onClick={handleAddAlias} disabled={!newAlias}>
                    <IconPlus size={12} /> 添加
                  </Button>
                </div>
              </div>

              {/* 标签 */}
              <div>
                <label className="text-xs font-medium text-gh-text-muted block mb-1.5">标签</label>
                <div className="flex flex-wrap gap-1.5">
                  {tags.map((t) => {
                    const active = tagIds.includes(t.id)
                    return (
                      <button
                        key={t.id}
                        onClick={() =>
                          setTagIds(active ? tagIds.filter((x) => x !== t.id) : [...tagIds, t.id])
                        }
                        className={`px-2.5 py-1 text-xs font-medium rounded-full border transition-all ${
                          active
                            ? 'border-transparent'
                            : 'border-gh-border text-gh-text-muted hover:border-gh-text-muted'
                        }`}
                        style={
                          active
                            ? {
                                background: t.color + '20',
                                borderColor: t.color + '50',
                                color: t.color
                              }
                            : undefined
                        }
                      >
                        {active && '✓ '}{t.name}
                      </button>
                    )
                  })}
                </div>
              </div>
            </>
          )}

          {activeTab === 'credentials' && (
            <>
              {email.email_account_id ? (
                <>
                  {/* 状态 */}
                  <Select
                    label="状态"
                    value={credStatus}
                    onChange={setCredStatus}
                    options={[
                      { value: 'active', label: '正常' },
                      { value: 'inactive', label: '停用' }
                    ]}
                  />

                  {/* 凭证信息 */}
                  <div className="pt-3 border-t border-gh-border">
                    <label className="text-xs font-semibold text-gh-text-muted block mb-3">
                      凭证信息
                    </label>
                    <div className="space-y-2">
                      {/* 密码 - 带显隐切换 */}
                      <div className="flex flex-col gap-1.5">
                        <label className="text-xs font-medium text-gh-text-muted">
                          {isOutlook ? '密码' : 'IMAP 授权码 / 应用密码'}
                        </label>
                        <div className="relative">
                          <input
                            type={showPwd ? 'text' : 'password'}
                            value={credPwd}
                            onChange={(e) => setCredPwd(e.target.value)}
                            placeholder={isOutlook ? 'Outlook 密码' : 'IMAP 授权码或应用密码'}
                            className="w-full bg-gh-canvas-inset border border-gh-border rounded-md pl-3 pr-10 py-1.5 text-sm text-gh-text font-mono placeholder-gh-text-secondary focus:outline-none focus:border-gh-accent focus:ring-1 focus:ring-gh-accent/50 transition-colors"
                          />
                          <button
                            type="button"
                            onClick={() => setShowPwd(!showPwd)}
                            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded text-gh-text-muted hover:text-gh-text transition-colors"
                            title={showPwd ? '隐藏密码' : '显示密码'}
                          >
                            {showPwd ? (
                              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                                <line x1="1" y1="1" x2="23" y2="23" />
                              </svg>
                            ) : (
                              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                                <circle cx="12" cy="12" r="3" />
                              </svg>
                            )}
                          </button>
                        </div>
                      </div>
                      {isOutlook && (
                        <>
                          <Input
                            label="Client ID"
                            value={credCid}
                            onChange={(e) => setCredCid(e.target.value)}
                            placeholder="OAuth Client ID"
                          />
                          <div>
                            <label className="text-xs font-medium text-gh-text-muted block mb-1.5">
                              Refresh Token（不填写则不更新）
                            </label>
                            <textarea
                              value={credRtk}
                              onChange={(e) => setCredRtk(e.target.value)}
                              placeholder="OAuth Refresh Token"
                              rows={3}
                              className="w-full bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-2 text-sm text-gh-text font-mono focus:outline-none focus:border-gh-accent"
                            />
                          </div>
                        </>
                      )}
                    </div>
                  </div>

                </>
              ) : (
                <div className="text-center py-8 text-gh-text-muted text-sm">
                  该邮箱没有关联的账户，无法管理凭证
                </div>
              )}
            </>
          )}
        </div>
      )}
    </Modal>
  )
}

// ========== SSE 进度条（增强版：实时成功/失败计数 + 最近账号列表 + 完成摘要） ==========
const SSEProgressBar: React.FC<{
  progress: SSERefreshEvent | null
  running: boolean
  onClose: () => void
}> = ({ progress, running, onClose }) => {
  const [recentItems, setRecentItems] = useState<Array<{ email: string; success: boolean }>>([])
  const [showComplete, setShowComplete] = useState(false)
  const completeTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null)

  // Track per-account results in real-time
  useEffect(() => {
    if (progress?.type === 'progress' && progress.email) {
      setRecentItems((prev) => {
        const next = [{ email: progress.email!, success: !!progress.success }, ...prev]
        return next.slice(0, 5) // keep last 5
      })
    }
    if (progress?.type === 'complete') {
      setShowComplete(true)
      // Auto-dismiss after 4 seconds
      completeTimerRef.current = setTimeout(() => {
        setShowComplete(false)
        onClose()
      }, 4000)
    }
    return () => {
      if (completeTimerRef.current) clearTimeout(completeTimerRef.current)
    }
  }, [progress, onClose])

  // Reset on new run
  useEffect(() => {
    if (running) {
      setRecentItems([])
      setShowComplete(false)
    }
  }, [running])

  if (!running && !showComplete) return null

  const current = progress?.current ?? 0
  const total = progress?.total ?? 1
  const pct = total > 0 ? Math.round((current / total) * 100) : 0
  // complete 事件的 success/failed 是总数，progress 事件从 recentItems 累计
  const isComplete = progress?.type === 'complete' || showComplete
  const successCount: number = isComplete
    ? (typeof progress?.success === 'number' ? progress.success : recentItems.filter((x) => x.success).length)
    : recentItems.filter((x) => x.success).length
  const failCount: number = isComplete
    ? (typeof progress?.failed === 'number' ? progress.failed : recentItems.filter((x) => !x.success).length)
    : recentItems.filter((x) => !x.success).length

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      className="border-b border-gh-border bg-gh-canvas-subtle overflow-hidden"
    >
      <div className="px-6 py-3">
        {/* 头部：标题 + 计数 */}
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center gap-2.5">
            {isComplete ? (
              <svg className="h-4 w-4 text-gh-success" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
              </svg>
            ) : (
              <svg className="animate-spin h-4 w-4 text-gh-accent" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
                <path d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" fill="currentColor" />
              </svg>
            )}
            <span className="text-sm font-semibold text-gh-text">
              {isComplete ? '刷新完成' : '正在刷新 Token...'}
            </span>
            {/* 实时成功/失败计数 */}
            <div className="flex items-center gap-2 text-xs font-mono">
              <span className="flex items-center gap-1 text-gh-success">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-gh-success" />
                {successCount}
              </span>
              <span className="flex items-center gap-1 text-gh-danger">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-gh-danger" />
                {failCount}
              </span>
              <span className="text-gh-text-secondary">
                {current}/{total}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* 当前处理的邮箱 */}
            {!isComplete && progress?.email && (
              <span className="text-xs text-gh-text-secondary font-mono truncate max-w-56" title={progress.email}>
                {progress.email}
              </span>
            )}
            {isComplete && (
              <span className="text-xs text-gh-text-secondary">
                {failCount === 0 ? '全部成功 ✓' : `${failCount} 个失败`}
              </span>
            )}
            <button
              onClick={() => { setShowComplete(false); onClose() }}
              className="p-1 rounded-md text-gh-text-muted hover:text-gh-text hover:bg-gh-border/50 transition-colors"
            >
              <IconX size={14} />
            </button>
          </div>
        </div>

        {/* 进度条 */}
        <div className="h-1.5 bg-gh-canvas-inset rounded-full overflow-hidden mb-2">
          <motion.div
            className={`h-full rounded-full transition-colors duration-500 ${
              isComplete
                ? failCount > 0 ? 'bg-gradient-to-r from-gh-success via-gh-warning to-gh-danger' : 'bg-gh-success'
                : 'bg-gradient-to-r from-gh-accent to-gh-purple'
            }`}
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ type: 'spring', stiffness: 80, damping: 18 }}
          />
        </div>

        {/* 最近处理的账号列表 */}
        {recentItems.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            {recentItems.map((item, i) => (
              <span
                key={`${item.email}-${i}`}
                className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-mono ${
                  item.success
                    ? 'bg-gh-success/10 text-gh-success border border-gh-success/20'
                    : 'bg-gh-danger/10 text-gh-danger border border-gh-danger/20'
                }`}
                title={item.email}
              >
                <span className={`inline-block w-1 h-1 rounded-full ${item.success ? 'bg-gh-success' : 'bg-gh-danger'}`} />
                {item.email.length > 28 ? item.email.slice(0, 28) + '…' : item.email}
              </span>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  )
}

// ========== 刷新确认弹窗 ==========
interface RefreshPreviewItem {
  id: number
  email: string
  provider?: string
  status?: string
  last_error?: string
}

const RefreshConfirmModal: React.FC<{
  open: boolean
  mode: 'all' | 'failed'
  accounts: RefreshPreviewItem[]
  loading: boolean
  onConfirm: () => void
  onCancel: () => void
}> = ({ open, mode, accounts, loading, onConfirm, onCancel }) => {
  const title = mode === 'all' ? '刷新全部账户' : '刷新失败账户'
  const description = mode === 'all'
    ? '以下活跃账户将被刷新 Token，此操作可能需要较长时间。'
    : '以下上次刷新失败的账户将被重新刷新。'

  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onCancel} disabled={loading}>取消</Button>
          <Button variant="primary" onClick={onConfirm} loading={loading} disabled={loading || accounts.length === 0}>
            确认刷新 ({accounts.length})
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-sm text-gh-text-secondary">{description}</p>

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <svg className="animate-spin h-6 w-6 text-gh-accent" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
              <path d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" fill="currentColor" />
            </svg>
            <span className="ml-2 text-sm text-gh-text-secondary">正在获取账户列表…</span>
          </div>
        ) : accounts.length === 0 ? (
          <div className="text-center py-8 text-gh-text-secondary text-sm">
            <IconMail size={32} className="mx-auto mb-2 opacity-30" />
            {mode === 'all' ? '没有需要刷新的账户' : '没有刷新失败的账户'}
          </div>
        ) : (
          <>
            <div className="flex items-center gap-3 text-xs text-gh-text-secondary px-1">
              <span>共 <span className="text-gh-text font-semibold">{accounts.length}</span> 个账户待刷新</span>
            </div>
            <div className="max-h-64 overflow-y-auto border border-gh-border rounded-lg">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-gh-canvas-subtle">
                  <tr className="border-b border-gh-border text-left text-xs text-gh-text-muted">
                    <th className="px-3 py-2 font-medium">邮箱</th>
                    <th className="px-3 py-2 font-medium w-16">服务商</th>
                    {mode === 'failed' && (
                      <th className="px-3 py-2 font-medium">上次错误</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((a) => (
                    <tr key={a.id} className="border-b border-gh-border/50 hover:bg-gh-border/20">
                      <td className="px-3 py-2 font-mono text-xs text-gh-text truncate max-w-56">{a.email}</td>
                      <td className="px-3 py-2 text-xs text-gh-text-secondary">{a.provider || '—'}</td>
                      {mode === 'failed' && (
                        <td className="px-3 py-2 text-xs text-gh-danger truncate max-w-48" title={a.last_error}>
                          {a.last_error || '—'}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}

// ========== 主页面 ==========
export const Accounts: React.FC = () => {
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null)
  const [selectedEmail, setSelectedEmail] = useState<UsableEmail | null>(null)
  const [selectedEmailIds, setSelectedEmailIds] = useState<Set<number>>(new Set())
  const [poolEmailIds, setPoolEmailIds] = useState<Set<number>>(new Set())
  const [bulkGroupOpen, setBulkGroupOpen] = useState(false)
  const [bulkGroupId, setBulkGroupId] = useState<number | ''>('')
  const [bulkLoading, setBulkLoading] = useState(false)
  const [refreshProgress, setRefreshProgress] = useState<SSERefreshEvent | null>(null)
  const [refreshRunning, setRefreshRunning] = useState(false)
  const [refreshConfirm, setRefreshConfirm] = useState<'all' | 'failed' | null>(null)
  const [refreshPreviewAccounts, setRefreshPreviewAccounts] = useState<RefreshPreviewItem[]>([])
  const [refreshPreviewLoading, setRefreshPreviewLoading] = useState(false)
  const { emails, accounts, groups, refreshAccounts, refreshEmails } = useApp()
  const { toast } = useToast()
  const refreshTimeoutRef = React.useRef<ReturnType<typeof setTimeout> | null>(null)

  const selectedEmails = useMemo(
    () => emails.filter((email) => selectedEmailIds.has(email.id)),
    [emails, selectedEmailIds]
  )

  const selectedAccountIds = useMemo(
    () => Array.from(new Set(
      selectedEmails
        .map((email) => email.email_account_id)
        .filter((id): id is number => typeof id === 'number')
    )),
    [selectedEmails]
  )

  const refreshPoolEmailIds = React.useCallback(async () => {
    const entries = await api.listPoolEntries()
    setPoolEmailIds(getPoolEmailIdSet(entries))
  }, [])

  useEffect(() => {
    refreshPoolEmailIds().catch(() => setPoolEmailIds(new Set()))
  }, [refreshPoolEmailIds])

  // 安全超时：防止 SSE 流异常时进度条永久卡住（兜底机制，正常由 complete 事件关闭）
  useEffect(() => {
    if (refreshRunning) {
      refreshTimeoutRef.current = setTimeout(() => {
        setRefreshRunning(false)
        toast('刷新超时（服务器可能已断开），请重试', 'error')
      }, 10 * 60 * 1000) // 10 分钟超时
    }
    return () => {
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current)
        refreshTimeoutRef.current = null
      }
    }
  }, [refreshRunning, toast])

  // 当选中的邮箱被删除时清空
  useEffect(() => {
    if (selectedEmail && !emails.find((e) => e.id === selectedEmail.id)) {
      setSelectedEmail(null)
    }
    const validEmailIds = new Set(emails.map((e) => e.id))
    setSelectedEmailIds((prev) => {
      const next = new Set(Array.from(prev).filter((id) => validEmailIds.has(id)))
      return next.size === prev.size ? prev : next
    })
  }, [emails, selectedEmail])

  const toggleSelectEmail = (emailId: number): void => {
    setSelectedEmailIds((prev) => {
      const next = new Set(prev)
      if (next.has(emailId)) {
        next.delete(emailId)
      } else {
        next.add(emailId)
      }
      return next
    })
  }

  // 打开刷新确认弹窗并加载待刷新账户列表
  const openRefreshConfirm = async (mode: 'all' | 'failed'): Promise<void> => {
    setRefreshConfirm(mode)
    setRefreshPreviewLoading(true)
    setRefreshPreviewAccounts([])
    try {
      if (mode === 'all') {
        const accts = await api.listEmailAccounts()
        setRefreshPreviewAccounts(
          accts
            .filter((a: any) => a.status === 'active')
            .map((a: any) => ({
              id: a.id,
              email: a.primary_address || a.display_name || '—',
              provider: a.provider,
              status: a.status,
            }))
        )
      } else {
        // 获取刷新失败的账户
        const failedLogs = await api.getFailedRefreshLogs()
        // 从 accounts 中匹配失败账户信息
        const currentAccounts = accounts.length > 0 ? accounts : await api.listEmailAccounts()
        const failedMap = new Map<string, string>() // email -> error_detail
        failedLogs.logs?.forEach((log: any) => {
          if (log.email && !failedMap.has(log.email)) {
            failedMap.set(log.email, log.error_detail || log.message || '')
          }
        })
        setRefreshPreviewAccounts(
          Array.from(failedMap.entries()).map(([email, error]) => {
            const matched = currentAccounts.find((a: any) => a.primary_address === email)
            return {
              id: matched?.id ?? 0,
              email,
              provider: matched?.provider,
              last_error: error,
            }
          })
        )
      }
    } catch (err: any) {
      toast(err.message, 'error')
      setRefreshConfirm(null)
    } finally {
      setRefreshPreviewLoading(false)
    }
  }

  const handleBulkGroup = async (): Promise<void> => {
    const ids = Array.from(selectedEmailIds)
    if (ids.length === 0) return
    setBulkLoading(true)
    try {
      await Promise.all(ids.map((id) => api.organizeUsableEmail(id, { group_id: bulkGroupId || null })))
      await refreshEmails()
      toast(`已更新 ${ids.length} 个邮箱的分组`, 'success')
      setSelectedEmailIds(new Set())
      setBulkGroupOpen(false)
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setBulkLoading(false)
    }
  }

  const handleBulkAddToPool = async (): Promise<void> => {
    if (selectedEmails.length === 0) return
    setBulkLoading(true)
    try {
      const currentPoolIds = poolEmailIds.size > 0
        ? poolEmailIds
        : getPoolEmailIdSet(await api.listPoolEntries())
      const candidates = selectedEmails.filter(
        (email) => !!email.email_account_id && !currentPoolIds.has(email.id)
      )
      if (candidates.length === 0) {
        toast('选中的邮箱都已在邮箱池，或没有关联账户', 'info')
        return
      }
      const results = await Promise.allSettled(candidates.map((email) => api.addPoolEntry(email.id)))
      const success = results.filter((r) => r.status === 'fulfilled').length
      const failed = results.length - success
      await refreshPoolEmailIds()
      if (success > 0) {
        toast(`已加入邮箱池 ${success} 个邮箱`, failed > 0 ? 'info' : 'success')
        setSelectedEmailIds(new Set())
      }
      if (failed > 0) toast(`${failed} 个邮箱加入失败或已存在`, 'error')
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setBulkLoading(false)
    }
  }

  const doRefresh = async (): Promise<void> => {
    const mode = refreshConfirm
    setRefreshConfirm(null)
    if (!mode) return
    setRefreshRunning(true)
    setRefreshProgress(null)
    const url = mode === 'all' ? '/email-accounts/refresh-all' : '/email-accounts/refresh-failed'
    try {
      await streamRefresh(url, undefined, (e: SSERefreshEvent) => {
        setRefreshProgress(e)
        if (e.type === 'complete') {
          setRefreshRunning(false)
          toast(
            `刷新完成: 成功 ${e.success ?? 0}, 失败 ${e.failed ?? 0}`,
            (e.failed ?? 0) > 0 ? 'error' : 'success'
          )
          refreshAccounts()
          refreshEmails()
        }
      })
    } catch (err: any) {
      toast(err.message, 'error')
      setRefreshRunning(false)
    }
  }

  const handleRefreshSelected = async (): Promise<void> => {
    const ids = selectedAccountIds
    if (ids.length === 0) return
    setRefreshRunning(true)
    setRefreshProgress(null)
    try {
      await streamRefresh(
        '/email-accounts/refresh/selected',
        { account_ids: ids },
        (e: SSERefreshEvent) => {
          setRefreshProgress(e)
          if (e.type === 'complete') {
            setRefreshRunning(false)
            toast(
              `刷新完成: 成功 ${e.success ?? 0}, 失败 ${e.failed ?? 0}`,
              (e.failed ?? 0) > 0 ? 'error' : 'success'
            )
            setSelectedEmailIds(new Set())
            refreshAccounts()
            refreshEmails()
          }
        }
      )
    } catch (err: any) {
      toast(err.message, 'error')
      setRefreshRunning(false)
    }
  }

  const handleRefreshAccountDone = (): void => {
    refreshAccounts()
    refreshEmails()
  }

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
      <Topbar
        title="账号管理"
        subtitle="管理所有邮箱账户、可用邮箱和分组"
        actions={
          <div className="flex items-center gap-1.5">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => openRefreshConfirm('all')}
              disabled={refreshRunning}
              title="查看并确认刷新全部活跃账户的 Token"
            >
              <IconRefresh size={14} /> 刷新全部
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => openRefreshConfirm('failed')}
              disabled={refreshRunning}
              title="查看并确认刷新上次失败的账户"
            >
              <IconAlertTriangle size={14} /> 刷新失败
            </Button>
            {selectedEmailIds.size > 0 && (
              <>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setBulkGroupId(selectedGroupId ?? '')
                    setBulkGroupOpen(true)
                  }}
                  disabled={bulkLoading}
                >
                  <IconTag size={14} /> 分组选中 ({selectedEmailIds.size})
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleBulkAddToPool}
                  disabled={bulkLoading}
                >
                  <IconFolderPlus size={14} /> 加入邮箱池 ({selectedEmailIds.size})
                </Button>
                {selectedAccountIds.length > 0 && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleRefreshSelected}
                    disabled={refreshRunning}
                  >
                    <IconRefresh size={14} /> 刷新选中账户 ({selectedAccountIds.length})
                  </Button>
                )}
              </>
            )}
          </div>
        }
      />

      <SSEProgressBar
        progress={refreshProgress}
        running={refreshRunning}
        onClose={() => setRefreshRunning(false)}
      />

      <RefreshConfirmModal
        open={refreshConfirm !== null}
        mode={refreshConfirm ?? 'all'}
        accounts={refreshPreviewAccounts}
        loading={refreshPreviewLoading}
        onConfirm={doRefresh}
        onCancel={() => setRefreshConfirm(null)}
      />

      <Modal
        open={bulkGroupOpen}
        onClose={() => setBulkGroupOpen(false)}
        title="批量分组"
        footer={
          <>
            <Button variant="ghost" onClick={() => setBulkGroupOpen(false)} disabled={bulkLoading}>取消</Button>
            <Button variant="primary" onClick={handleBulkGroup} loading={bulkLoading} disabled={selectedEmailIds.size === 0}>
              更新分组 ({selectedEmailIds.size})
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <p className="text-sm text-gh-text-secondary">
            将选中的 {selectedEmailIds.size} 个邮箱移动到目标分组。
          </p>
          <Select
            label="目标分组"
            value={bulkGroupId}
            onChange={(v) => setBulkGroupId(v ? Number(v) : '')}
            options={[
              { value: '', label: '无分组' },
              ...groups.map((g) => ({ value: g.id, label: g.name }))
            ]}
          />
        </div>
      </Modal>

      <div className="flex-1 flex min-h-0 overflow-hidden">
        <GroupSidebar
          selectedGroupId={selectedGroupId}
          onSelect={(id) => {
            setSelectedGroupId(id)
            setSelectedEmail(null)
          }}
        />
        <EmailList
          groupId={selectedGroupId}
          selectedEmailId={selectedEmail?.id || null}
          onSelect={setSelectedEmail}
          selectedEmailIds={selectedEmailIds}
          poolEmailIds={poolEmailIds}
          onToggleEmailSelect={toggleSelectEmail}
          onRefreshAccount={handleRefreshAccountDone}
          onPoolChanged={refreshPoolEmailIds}
        />
        <EmailDetail email={selectedEmail} />
      </div>
    </div>
  )
}
