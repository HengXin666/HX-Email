import React, { useState, useEffect, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Topbar } from '../components/layout'
import { useApp } from '../store/AppContext'
import { useToast } from '../components/ui/Toast'
import { Button, Modal, Input, Badge, Card } from '../components/ui/Primitives'
import {
  IconFolderPlus,
  IconEdit,
  IconTrash,
  IconPlus,
  IconCopy,
  IconCheck,
  IconMail,
  IconKey,
  IconMoreVertical,
  IconStar,
  IconRefresh,
  IconTag,
  IconSettings,
  IconLink,
  IconClock,
  IconShield,
  IconZap,
  IconAt,
  IconUser,
  IconDownload,
  IconUpload,
  IconAlertTriangle,
  IconX
} from '../components/icons'
import { api, streamRefresh } from '../api/client'
import type { AccountImportResult, UsableEmail, VerificationMatch, SSERefreshEvent } from '../types'

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
    if (!confirm('确定删除该分组？')) return
    try {
      await deleteGroup(id)
      if (selectedGroupId === id) onSelect(null)
      toast('分组已删除', 'success')
    } catch (err: any) {
      toast(err.message, 'error')
    }
  }

  return (
    <div className="w-56 shrink-0 h-full border-r border-gh-border bg-gh-canvas-subtle/50 flex flex-col">
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

      {/* 编辑分组 */}
      <EditGroupModal
        groupId={editingGroup}
        onClose={() => setEditingGroup(null)}
        onUpdate={updateGroup}
        onDelete={deleteGroup}
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
  const [showMenu, setShowMenu] = useState(false)
  return (
    <div className="relative group">
      <button
        onClick={onClick}
        className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors ${
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
      <button
        onClick={(e) => {
          e.stopPropagation()
          setShowMenu((s) => !s)
        }}
        className="absolute right-1 top-1/2 -translate-y-1/2 p-1 rounded-md text-gh-text-secondary hover:text-gh-text hover:bg-gh-border/50 opacity-0 group-hover:opacity-100 transition-opacity"
      >
        <IconMoreVertical size={14} />
      </button>
      <AnimatePresence>
        {showMenu && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setShowMenu(false)} />
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="absolute right-0 top-full mt-1 z-20 w-32 bg-gh-canvas-subtle border border-gh-border rounded-md shadow-xl overflow-hidden"
            >
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onEdit()
                  setShowMenu(false)
                }}
                className="w-full px-3 py-1.5 text-sm text-left text-gh-text hover:bg-gh-border/40 flex items-center gap-2"
              >
                <IconEdit size={12} /> 编辑
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete()
                  setShowMenu(false)
                }}
                className="w-full px-3 py-1.5 text-sm text-left text-gh-danger hover:bg-gh-danger/10 flex items-center gap-2"
              >
                <IconTrash size={12} /> 删除
              </button>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}

const EditGroupModal: React.FC<{
  groupId: number | null
  onClose: () => void
  onUpdate: (id: number, name: string, color: string) => Promise<any>
  onDelete: (id: number) => Promise<any>
}> = ({ groupId, onClose, onUpdate, onDelete }) => {
  const { groups } = useApp()
  const { toast } = useToast()
  const g = groups.find((x) => x.id === groupId)
  const [name, setName] = useState(g?.name || '')
  const [color, setColor] = useState(g?.color || COLORS[0])

  useEffect(() => {
    if (g) {
      setName(g.name)
      setColor(g.color)
    }
  }, [g])

  const handleSave = async () => {
    if (!g || !name.trim()) return
    try {
      await onUpdate(g.id, name.trim(), color)
      toast('分组已更新', 'success')
      onClose()
    } catch (err: any) {
      toast(err.message, 'error')
    }
  }

  return (
    <Modal
      open={!!groupId}
      onClose={onClose}
      title="编辑分组"
      footer={
        <>
          <Button variant="danger" onClick={async () => {
            if (g && confirm('确定删除？')) {
              await onDelete(g.id)
              onClose()
            }
          }}>
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
      </div>
    </Modal>
  )
}

// ========== 中间：邮箱卡片列表 ==========
const EmailList: React.FC<{
  groupId: number | null
  selectedEmailId: number | null
  onSelect: (e: UsableEmail) => void
  selectedForRefresh: Set<number>
  onToggleRefreshSelect: (accountId: number) => void
  onRefreshAccount: () => void
}> = ({ groupId, selectedEmailId, onSelect, selectedForRefresh, onToggleRefreshSelect, onRefreshAccount }) => {
  const { emails, groups, refreshEmails } = useApp()
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

  return (
    <div className="w-80 shrink-0 h-full border-r border-gh-border bg-gh-canvas flex flex-col">
      <div className="h-12 px-3 flex items-center gap-2 border-b border-gh-border">
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
          onClick={refreshEmails}
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
              selectedForRefresh={e.email_account_id ? selectedForRefresh.has(e.email_account_id) : false}
              onToggleRefreshSelect={e.email_account_id ? () => onToggleRefreshSelect(e.email_account_id!) : undefined}
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

      <AddEmailModal open={showAdd} onClose={() => setShowAdd(false)} defaultGroupId={groupId} />
      <EmailSettingsModal
        emailId={showSettings}
        onClose={() => setShowSettings(null)}
      />
    </div>
  )
}

const EmailCard: React.FC<{
  email: UsableEmail
  selected: boolean
  onClick: () => void
  onSettings: () => void
  selectedForRefresh?: boolean
  onToggleRefreshSelect?: () => void
  onRefreshAccount?: () => void
}> = ({ email, selected, onClick, onSettings, selectedForRefresh, onToggleRefreshSelect, onRefreshAccount }) => {
  const { toast } = useToast()
  const [copied, setCopied] = useState(false)
  const [loadingCode, setLoadingCode] = useState(false)
  const [showAliases, setShowAliases] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const handleRefresh = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!email.email_account_id) return
    setRefreshing(true)
    try {
      const res = await api.refreshAccount(email.email_account_id)
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
      const match = res.matches[0]
      if (match?.code) {
        navigator.clipboard.writeText(match.code)
        toast(`验证码 ${match.code} 已复制`, 'success')
      } else {
        toast('未找到验证码', 'info')
      }
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setLoadingCode(false)
    }
  }

  const kindLabel: Record<string, string> = {
    primary: '主',
    alias: '别名',
    custom: '自定',
    temp: '临时'
  }

  return (
    <motion.div layout initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      <Card selected={selected} onClick={onClick} className="p-3">
        <div className="flex items-start gap-2">
          {email.email_account_id && onToggleRefreshSelect ? (
            <div className="shrink-0 pt-1" onClick={(e) => e.stopPropagation()}>
              <input
                type="checkbox"
                checked={!!selectedForRefresh}
                onChange={onToggleRefreshSelect}
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
              <Badge color={
                email.kind === 'primary' ? '#58a6ff' :
                email.kind === 'alias' ? '#a371f7' :
                email.kind === 'temp' ? '#f0883e' : '#6e7681'
              }>
                {kindLabel[email.kind]}
              </Badge>
            </div>
            <button
              onClick={handleCopy}
              className="text-sm text-gh-text font-medium truncate max-w-full hover:text-gh-accent transition-colors group inline-flex items-center gap-1"
            >
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
            <IconClock size={10} /> {email.updated_at || '—'}
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
                <IconZap size={13} />
              )}
            </button>
            {email.email_account_id && onRefreshAccount ? (
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
          </div>
        </div>
      </Card>
    </motion.div>
  )
}

// ========== 右侧：邮件详情 ==========
const EmailDetail: React.FC<{ email: UsableEmail | null }> = ({ email }) => {
  const { accounts } = useApp()
  const [messages, setMessages] = React.useState<any[]>([])
  const [codes, setCodes] = React.useState<any[]>([])
  const [links, setLinks] = React.useState<any[]>([])
  const [bindings, setBindings] = React.useState<any[]>([])
  const [loading, setLoading] = React.useState(false)
  const [tab, setTab] = React.useState<'messages' | 'verify' | 'bindings'>('messages')

  const account = accounts.find((a) => a.id === email?.email_account_id)
  const aliases = account?.usable_emails.filter((u) => u.kind === 'alias') || []

  useEffect(() => {
    if (!email) return
    const load = async () => {
      setLoading(true)
      try {
        if (email.kind === 'temp') {
          const [m, c, l] = await Promise.all([
            api.tempMessages(email.id),
            api.tempCodes(email.id),
            api.tempLinks(email.id)
          ])
          setMessages(m)
          setCodes(c)
          setLinks(l)
        } else {
          const res = await api.readVerification(email.id)
          setMessages(res.matches.map((x, i) => ({
            id: `v_${i}`,
            from_address: x.recipient_address,
            subject: x.subject,
            text: `验证码: ${x.code || '—'}\n链接: ${x.link || '—'}`,
            received_at: x.received_at
          })))
          setCodes(res.matches.filter((x) => x.code).map((x, i) => ({
            message_id: `v_${i}`,
            code: x.code
          })))
          setLinks(res.matches.filter((x) => x.link).map((x, i) => ({
            message_id: `v_${i}`,
            url: x.link
          })))
        }
        const b = await api.listBindings(email.id)
        setBindings(b)
      } catch (err) {
        console.error(err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [email])

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
    <div className="flex-1 flex flex-col min-w-0 h-full">
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
          <div className="mt-3 pt-3 border-t border-gh-border/60 flex items-center gap-2 text-xs text-gh-text-secondary">
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
      <div className="flex items-center gap-1 px-6 border-b border-gh-border bg-gh-canvas-subtle/40">
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
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <AnimatePresence mode="wait">
          {loading ? (
            <div className="text-center py-12 text-gh-text-secondary text-sm">加载中...</div>
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
  if (messages.length === 0) {
    return <div className="text-center py-12 text-gh-text-secondary text-sm">暂无邮件</div>
  }
  return (
    <div className="space-y-2">
      {messages.map((m, i) => (
        <motion.div
          key={m.id}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.03 }}
          className="rounded-lg border border-gh-border bg-gh-canvas-subtle p-3 hover:border-gh-text-muted transition-colors"
        >
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-md bg-gh-accent/10 text-gh-accent flex items-center justify-center shrink-0">
              <IconMail size={14} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2 mb-0.5">
                <div className="text-sm font-medium text-gh-text truncate">{m.subject}</div>
                {m.received_at && (
                  <span className="text-[11px] text-gh-text-secondary whitespace-nowrap">
                    {m.received_at}
                  </span>
                )}
              </div>
              <div className="text-xs text-gh-text-muted truncate">{m.from_address}</div>
              {m.text && (
                <div className="mt-2 text-xs text-gh-text-secondary line-clamp-2 font-mono bg-gh-canvas-inset p-2 rounded">
                  {m.text}
                </div>
              )}
            </div>
          </div>
        </motion.div>
      ))}
    </div>
  )
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

// ========== 添加邮箱 Modal ==========
const AddEmailModal: React.FC<{
  open: boolean
  onClose: () => void
  defaultGroupId: number | null
}> = ({ open, onClose, defaultGroupId }) => {
  const { createEmail, createAccount, refreshEmails } = useApp()
  const { toast } = useToast()
  const [mode, setMode] = useState<'simple' | 'account'>('simple')
  const [address, setAddress] = useState('')
  const [label, setLabel] = useState('')
  const [provider, setProvider] = useState('gmail')
  const [displayName, setDisplayName] = useState('')
  const [aliases, setAliases] = useState<string[]>([])
  const [newAlias, setNewAlias] = useState('')
  const [loading, setLoading] = useState(false)

  const reset = () => {
    setAddress('')
    setLabel('')
    setDisplayName('')
    setAliases([])
    setNewAlias('')
  }

  const handleSave = async () => {
    setLoading(true)
    try {
      if (mode === 'simple') {
        if (!address) return
        await createEmail(address, label, defaultGroupId)
        toast('邮箱已添加', 'success')
      } else {
        if (!address || !displayName) return
        await createAccount({
          provider,
          primary_address: address,
          display_name: displayName,
          alias_addresses: aliases
        })
        toast('账户已创建', 'success')
      }
      reset()
      onClose()
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => {
        reset()
        onClose()
      }}
      title="添加邮箱"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={handleSave} loading={loading}>
            添加
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="flex p-1 bg-gh-canvas-inset border border-gh-border rounded-lg">
          <button
            onClick={() => setMode('simple')}
            className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-all ${
              mode === 'simple' ? 'bg-gh-canvas-subtle text-gh-text shadow-sm' : 'text-gh-text-muted'
            }`}
          >
            简单模式
          </button>
          <button
            onClick={() => setMode('account')}
            className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-all ${
              mode === 'account' ? 'bg-gh-canvas-subtle text-gh-text shadow-sm' : 'text-gh-text-muted'
            }`}
          >
            邮箱账户 (主 + 别名)
          </button>
        </div>

        <Input label="邮箱地址" value={address} onChange={(e) => setAddress(e.target.value)} placeholder="user@example.com" />

        {mode === 'simple' ? (
          <Input label="备注名称（可选）" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="例如：工作主邮箱" />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Input label="显示名称" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Alice" />
              <div>
                <label className="text-xs font-medium text-gh-text-muted block mb-1.5">服务商</label>
                <select
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  className="w-full bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-1.5 text-sm text-gh-text focus:outline-none focus:border-gh-accent"
                >
                  <option value="gmail">Gmail</option>
                  <option value="outlook">Outlook</option>
                  <option value="yahoo">Yahoo</option>
                  <option value="icloud">iCloud</option>
                  <option value="other">其他</option>
                </select>
              </div>
            </div>
            <div>
              <label className="text-xs font-medium text-gh-text-muted block mb-1.5">
                别名邮箱 ({aliases.length})
              </label>
              <div className="space-y-1.5 mb-2">
                {aliases.map((a, i) => (
                  <div key={i} className="flex items-center gap-2 bg-gh-canvas-inset border border-gh-border rounded-md px-2 py-1">
                    <IconAt size={12} className="text-gh-text-secondary" />
                    <span className="flex-1 text-sm text-gh-text font-mono">{a}</span>
                    <button
                      onClick={() => setAliases(aliases.filter((_, j) => j !== i))}
                      className="text-gh-text-muted hover:text-gh-danger p-0.5"
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
                    </button>
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <Input
                  value={newAlias}
                  onChange={(e) => setNewAlias(e.target.value)}
                  placeholder="alias@domain.com"
                  className="flex-1"
                />
                <Button
                  variant="secondary"
                  onClick={() => {
                    if (newAlias && !aliases.includes(newAlias)) {
                      setAliases([...aliases, newAlias])
                      setNewAlias('')
                    }
                  }}
                >
                  <IconPlus size={12} />
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}

// ========== 邮箱设置 Modal ==========
const EmailSettingsModal: React.FC<{
  emailId: number | null
  onClose: () => void
}> = ({ emailId, onClose }) => {
  const { emails, groups, tags, organizeEmail, addAlias, accounts } = useApp()
  const { toast } = useToast()
  const email = emails.find((e) => e.id === emailId)
  const [label, setLabel] = useState('')
  const [groupId, setGroupId] = useState<number | ''>('')
  const [tagIds, setTagIds] = useState<number[]>([])
  const [newAlias, setNewAlias] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (email) {
      setLabel(email.label || '')
      setGroupId(email.group?.id || '')
      setTagIds(email.tags?.map((t) => t.id) || [])
    }
  }, [email])

  const handleSave = async () => {
    if (!email) return
    setLoading(true)
    try {
      await organizeEmail(email.id, {
        label,
        group_id: groupId || null,
        tag_ids: tagIds
      })
      toast('设置已保存', 'success')
      onClose()
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleAddAlias = async () => {
    if (!email || !newAlias) return
    const acc = accounts.find((a) => a.id === email.email_account_id)
    if (!acc) {
      toast('该邮箱没有关联的账户', 'error')
      return
    }
    try {
      await addAlias(acc.id, newAlias)
      toast('别名已添加', 'success')
      setNewAlias('')
    } catch (err: any) {
      toast(err.message, 'error')
    }
  }

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
          <div className="px-3 py-2 rounded-md bg-gh-canvas-inset border border-gh-border">
            <div className="text-xs text-gh-text-secondary">邮箱地址</div>
            <div className="text-sm font-mono text-gh-text">{email.address}</div>
          </div>

          <Input label="备注名称" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="例如：主邮箱" />

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

          {email.email_account_id && (
            <div className="pt-3 border-t border-gh-border">
              <label className="text-xs font-medium text-gh-text-muted block mb-1.5">
                添加别名
              </label>
              <div className="flex gap-2">
                <Input
                  value={newAlias}
                  onChange={(e) => setNewAlias(e.target.value)}
                  placeholder="alias@domain.com"
                  className="flex-1"
                />
                <Button variant="secondary" onClick={handleAddAlias} disabled={!newAlias}>
                  添加
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}

const AccountImportModal: React.FC<{
  open: boolean
  onClose: () => void
}> = ({ open, onClose }) => {
  const { refreshAccounts, refreshEmails } = useApp()
  const { toast } = useToast()
  const [text, setText] = useState('')
  const [duplicateStrategy, setDuplicateStrategy] = useState('skip')
  const [result, setResult] = useState<AccountImportResult | null>(null)
  const [loading, setLoading] = useState<string | null>(null)

  const handleImport = async () => {
    setLoading('import')
    try {
      const imported = await api.importEmailAccounts(text, duplicateStrategy)
      setResult(imported)
      await Promise.all([refreshAccounts(), refreshEmails()])
      toast(`导入完成：成功 ${imported.imported}，跳过 ${imported.skipped}`, 'success')
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setLoading(null)
    }
  }

  const handleExport = async () => {
    setLoading('export')
    try {
      const exported = await api.exportEmailAccountsText()
      const blob = new Blob([exported], { type: 'text/plain;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `hx-email-accounts-${new Date().toISOString().slice(0, 10)}.txt`
      link.click()
      URL.revokeObjectURL(url)
      toast('账号已导出', 'success')
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setLoading(null)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="导入导出账号"
      size="xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>关闭</Button>
          <Button variant="secondary" onClick={handleExport} loading={loading === 'export'}>
            <IconDownload size={14} /> 导出
          </Button>
          <Button variant="primary" onClick={handleImport} loading={loading === 'import'}>
            <IconUpload size={14} /> 导入
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="w-full min-h-64 bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-2 text-sm text-gh-text font-mono focus:outline-none focus:border-gh-accent"
          placeholder="user@gmail.com----app-password----gmail&#10;user@qq.com----authorization-code----qq&#10;user@outlook.com----password----client_id----refresh_token"
        />
        <select
          value={duplicateStrategy}
          onChange={(e) => setDuplicateStrategy(e.target.value)}
          className="bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-1.5 text-sm text-gh-text"
        >
          <option value="skip">重复跳过</option>
          <option value="overwrite">重复覆盖</option>
        </select>
        {result && (
          <div className="rounded-md border border-gh-border bg-gh-canvas-inset p-3 text-sm text-gh-text-secondary">
            成功 {result.imported}，跳过 {result.skipped}，失败 {result.failed}
            {result.errors.length > 0 && (
              <div className="mt-2 space-y-1">
                {result.errors.map((error) => (
                  <div key={`${error.line}-${error.error}`}>第 {error.line} 行：{error.error}</div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  )
}

// ========== SSE 进度条 ==========
const SSEProgressBar: React.FC<{
  progress: SSERefreshEvent | null
  running: boolean
  onClose: () => void
}> = ({ progress, running, onClose }) => {
  if (!running) return null
  const current = progress?.current ?? 0
  const total = progress?.total ?? 1
  const pct = Math.round((current / total) * 100)

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      className="border-b border-gh-border bg-gh-canvas-subtle"
    >
      <div className="px-6 py-3">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2 text-sm">
            <svg className="animate-spin h-4 w-4 text-gh-accent" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
              <path d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" fill="currentColor" />
            </svg>
            <span className="text-gh-text font-medium">正在刷新 Token...</span>
            <span className="text-gh-text-secondary tabular-nums">
              {current} / {total}
            </span>
          </div>
          <div className="flex items-center gap-3">
            {progress?.email && (
              <span className="text-xs text-gh-text-secondary font-mono truncate max-w-48">
                {progress.email}
              </span>
            )}
            <button
              onClick={onClose}
              className="p-1 rounded-md text-gh-text-muted hover:text-gh-text hover:bg-gh-border/50 transition-colors"
            >
              <IconX size={14} />
            </button>
          </div>
        </div>
        <div className="h-1.5 bg-gh-canvas-inset rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-gradient-to-r from-gh-accent to-gh-purple rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ type: 'spring', stiffness: 100, damping: 20 }}
          />
        </div>
      </div>
    </motion.div>
  )
}

// ========== 主页面 ==========
export const Accounts: React.FC = () => {
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null)
  const [selectedEmail, setSelectedEmail] = useState<UsableEmail | null>(null)
  const [showImport, setShowImport] = useState(false)
  const [selectedForRefresh, setSelectedForRefresh] = useState<Set<number>>(new Set())
  const [refreshProgress, setRefreshProgress] = useState<SSERefreshEvent | null>(null)
  const [refreshRunning, setRefreshRunning] = useState(false)
  const { emails, refreshAccounts, refreshEmails } = useApp()
  const { toast } = useToast()

  // 当选中的邮箱被删除时清空
  useEffect(() => {
    if (selectedEmail && !emails.find((e) => e.id === selectedEmail.id)) {
      setSelectedEmail(null)
    }
  }, [emails, selectedEmail])

  const toggleSelectForRefresh = (accountId: number): void => {
    setSelectedForRefresh((prev) => {
      const next = new Set(prev)
      if (next.has(accountId)) {
        next.delete(accountId)
      } else {
        next.add(accountId)
      }
      return next
    })
  }

  const handleRefreshAll = async (): Promise<void> => {
    setRefreshRunning(true)
    setRefreshProgress(null)
    try {
      await streamRefresh('/email-accounts/refresh-all', undefined, (e: SSERefreshEvent) => {
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

  const handleRefreshFailed = async (): Promise<void> => {
    setRefreshRunning(true)
    setRefreshProgress(null)
    try {
      await streamRefresh('/email-accounts/refresh-failed', undefined, (e: SSERefreshEvent) => {
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
    const ids = Array.from(selectedForRefresh)
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
            setSelectedForRefresh(new Set())
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
    <div className="flex-1 flex flex-col min-w-0">
      <Topbar
        title="账号管理"
        subtitle="管理所有邮箱账户、可用邮箱和分组"
        actions={
          <div className="flex items-center gap-1.5">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleRefreshAll}
              loading={refreshRunning}
              disabled={refreshRunning}
            >
              <IconRefresh size={14} /> 刷新全部
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={handleRefreshFailed}
              disabled={refreshRunning}
            >
              <IconAlertTriangle size={14} /> 刷新失败
            </Button>
            {selectedForRefresh.size > 0 && (
              <Button
                variant="primary"
                size="sm"
                onClick={handleRefreshSelected}
                disabled={refreshRunning}
              >
                <IconRefresh size={14} /> 刷新选中 ({selectedForRefresh.size})
              </Button>
            )}
            <Button variant="secondary" onClick={() => setShowImport(true)}>
              <IconUpload size={14} /> 导入导出
            </Button>
          </div>
        }
      />

      <SSEProgressBar
        progress={refreshProgress}
        running={refreshRunning}
        onClose={() => setRefreshRunning(false)}
      />

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
          selectedForRefresh={selectedForRefresh}
          onToggleRefreshSelect={toggleSelectForRefresh}
          onRefreshAccount={handleRefreshAccountDone}
        />
        <EmailDetail email={selectedEmail} />
      </div>
      <AccountImportModal open={showImport} onClose={() => setShowImport(false)} />
    </div>
  )
}
