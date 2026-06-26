import React, { useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Topbar } from '../components/layout'
import { useApp } from '../store/AppContext'
import { useToast } from '../components/ui/Toast'
import { Button, Modal, Input, Badge, Card } from '../components/ui/Primitives'
import {
  IconPlus,
  IconEdit,
  IconTrash,
  IconServer,
  IconShield,
  IconSearch,
  IconLink
} from '../components/icons'
import { api } from '../api/client'

export const Platforms: React.FC = () => {
  const { platforms, emails, createPlatform, updatePlatform, deletePlatform, refreshPlatforms } = useApp()
  const { toast } = useToast()
  const [query, setQuery] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [selectedPlatformId, setSelectedPlatformId] = useState<number | null>(null)
  const [newName, setNewName] = useState('')

  const filtered = useMemo(
    () =>
      platforms.filter((p) =>
        !query ? true : p.name.toLowerCase().includes(query.toLowerCase())
      ),
    [platforms, query]
  )

  const selected = platforms.find((p) => p.id === selectedPlatformId)
  const selectedBindings = useMemo(
    () => (selected ? emails.filter((e) => (e.platform_binding_count || 0) > 0) : []),
    [selected, emails]
  )

  const handleCreate = async () => {
    if (!newName.trim()) return
    try {
      await createPlatform(newName.trim())
      toast('平台已创建', 'success')
      setNewName('')
      setShowCreate(false)
    } catch (err: any) {
      toast(err.message, 'error')
    }
  }

  const handleUpdate = async () => {
    if (!editingId || !newName.trim()) return
    try {
      await updatePlatform(editingId, newName.trim())
      toast('平台已更新', 'success')
      setEditingId(null)
      setNewName('')
    } catch (err: any) {
      toast(err.message, 'error')
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除该平台？')) return
    try {
      await deletePlatform(id)
      toast('平台已删除', 'success')
      if (selectedPlatformId === id) setSelectedPlatformId(null)
    } catch (err: any) {
      toast(err.message, 'error')
    }
  }

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
      <Topbar
        title="平台管理"
        subtitle="管理所有注册的平台及其邮箱绑定关系"
        actions={
          <Button variant="primary" onClick={() => setShowCreate(true)}>
            <IconPlus size={14} /> 新建平台
          </Button>
        }
      />

      <div className="flex-1 flex min-h-0">
        {/* 左：平台列表 */}
        <div className="w-80 shrink-0 h-full border-r border-gh-border bg-gh-canvas flex flex-col">
          <div className="px-3 py-3 border-b border-gh-border">
            <div className="relative">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索平台..."
                className="w-full bg-gh-canvas-inset border border-gh-border rounded-md pl-8 pr-3 py-1.5 text-sm text-gh-text placeholder-gh-text-secondary focus:outline-none focus:border-gh-accent"
              />
              <IconSearch size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gh-text-secondary" />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            <AnimatePresence>
              {filtered.map((p) => (
                <motion.div
                  key={p.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0 }}
                >
                  <Card
                    selected={selectedPlatformId === p.id}
                    onClick={() => setSelectedPlatformId(p.id)}
                    className="p-3"
                  >
                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-gh-accent to-gh-purple flex items-center justify-center text-white shrink-0">
                        <IconServer size={18} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-gh-text truncate">{p.name}</div>
                        <div className="text-xs text-gh-text-secondary mt-0.5">
                          {p.binding_count || 0} 个邮箱绑定
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-1 mt-2 pt-2 border-t border-gh-border/60" onClick={(e) => e.stopPropagation()}>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setEditingId(p.id)
                          setNewName(p.name)
                        }}
                      >
                        <IconEdit size={12} /> 编辑
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => handleDelete(p.id)}>
                        <IconTrash size={12} /> 删除
                      </Button>
                    </div>
                  </Card>
                </motion.div>
              ))}
            </AnimatePresence>
            {filtered.length === 0 && (
              <div className="text-center py-12 text-sm text-gh-text-secondary">
                暂无平台
              </div>
            )}
          </div>
        </div>

        {/* 右：平台详情 */}
        <div className="flex-1 flex flex-col min-w-0 h-full">
          {!selected ? (
            <div className="flex-1 flex items-center justify-center text-gh-text-secondary text-sm">
              <div className="text-center">
                <IconServer size={48} className="mx-auto mb-3 opacity-30" />
                <div>选择一个平台查看详情</div>
              </div>
            </div>
          ) : (
            <motion.div
              key={selected.id}
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex-1 flex flex-col"
            >
              <div className="px-6 py-5 border-b border-gh-border bg-gradient-to-r from-gh-canvas-subtle to-gh-canvas">
                <div className="flex items-center gap-4">
                  <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-gh-accent to-gh-purple flex items-center justify-center text-white shadow-lg shadow-gh-accent/30">
                    <IconServer size={24} />
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-gh-text">{selected.name}</h2>
                    <div className="text-sm text-gh-text-secondary mt-1">
                      {selected.binding_count || 0} 个绑定
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex-1 overflow-auto p-6">
                <h3 className="text-sm font-semibold text-gh-text mb-3 flex items-center gap-2">
                  <IconShield size={14} /> 绑定的邮箱
                </h3>
                <div className="space-y-2">
                  {selectedBindings.length === 0 ? (
                    <div className="text-center py-12 text-sm text-gh-text-secondary">
                      暂无邮箱绑定到此平台
                      <div className="mt-2 text-xs">
                        前往 "账号管理" 页面为邮箱绑定此平台
                      </div>
                    </div>
                  ) : (
                    selectedBindings.map((e) => (
                      <div
                        key={e.id}
                        className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-gh-border bg-gh-canvas-subtle"
                      >
                        <div className="w-8 h-8 rounded-md bg-gh-accent/10 text-gh-accent flex items-center justify-center">
                          <IconLink size={14} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-gh-text truncate">{e.address}</div>
                          {e.label && (
                            <div className="text-xs text-gh-text-secondary truncate">{e.label}</div>
                          )}
                        </div>
                        <Badge color="#3fb950">已绑定</Badge>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </div>

      {/* Create */}
      <Modal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        title="新建平台"
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowCreate(false)}>取消</Button>
            <Button variant="primary" onClick={handleCreate}>创建</Button>
          </>
        }
      >
        <Input label="平台名称" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="例如：GitHub" autoFocus />
      </Modal>

      {/* Edit */}
      <Modal
        open={!!editingId}
        onClose={() => setEditingId(null)}
        title="编辑平台"
        footer={
          <>
            <Button variant="ghost" onClick={() => setEditingId(null)}>取消</Button>
            <Button variant="primary" onClick={handleUpdate}>保存</Button>
          </>
        }
      >
        <Input label="平台名称" value={newName} onChange={(e) => setNewName(e.target.value)} />
      </Modal>
    </div>
  )
}
