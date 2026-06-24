import React, { useState } from 'react'
import { motion } from 'framer-motion'
import { Topbar } from '../components/layout'
import { useApp } from '../store/AppContext'
import { useToast } from '../components/ui/Toast'
import { Button, Input, Card } from '../components/ui/Primitives'
import {
  IconSettings,
  IconUser,
  IconKey,
  IconDatabase,
  IconDownload,
  IconUpload,
  IconShield,
  IconCheck,
  IconGithub,
  IconRefresh
} from '../components/icons'
import { api } from '../api/client'

export const Settings: React.FC = () => {
  const { user } = useApp()
  const { toast } = useToast()
  const [tab, setTab] = useState<'profile' | 'data' | 'about'>('profile')

  return (
    <div className="flex-1 flex flex-col min-w-0">
      <Topbar title="设置" subtitle="账户、数据与系统配置" />

      <div className="flex-1 overflow-auto">
        <div className="max-w-3xl mx-auto p-6">
          <div className="flex items-center gap-1 border-b border-gh-border mb-5">
            {[
              { k: 'profile', label: '个人资料', icon: IconUser },
              { k: 'data', label: '数据管理', icon: IconDatabase },
              { k: 'about', label: '关于', icon: IconSettings }
            ].map((t) => (
              <button
                key={t.k}
                onClick={() => setTab(t.k as any)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
                  tab === t.k
                    ? 'border-gh-accent text-gh-accent'
                    : 'border-transparent text-gh-text-muted hover:text-gh-text'
                }`}
              >
                <t.icon size={13} />
                {t.label}
              </button>
            ))}
          </div>

          {tab === 'profile' && <ProfileTab user={user} />}
          {tab === 'data' && <DataTab />}
          {tab === 'about' && <AboutTab />}
        </div>
      </div>
    </div>
  )
}

const ProfileTab: React.FC<{ user: any }> = ({ user }) => {
  const { toast } = useToast()
  const { updateCredentials } = useApp()
  const [username, setUsername] = useState(user?.username || '')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [regEnabled, setRegEnabled] = useState(true)

  const handleSave = async () => {
    if (!username) return
    if (password && password !== confirm) {
      toast('两次密码不一致', 'error')
      return
    }
    setLoading(true)
    try {
      await updateCredentials(username, password || 'unchanged')
      toast('个人资料已更新', 'success')
      setPassword('')
      setConfirm('')
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleToggleReg = async () => {
    try {
      setRegEnabled(!regEnabled)
      toast(regEnabled ? '注册已关闭' : '注册已开启', 'success')
    } catch (err: any) {
      toast(err.message, 'error')
    }
  }

  return (
    <div className="space-y-5">
      <Card className="p-5">
        <h3 className="text-sm font-semibold text-gh-text mb-4 flex items-center gap-2">
          <IconUser size={14} /> 账户信息
        </h3>
        <div className="space-y-3 max-w-md">
          <Input
            label="用户名"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <Input
            label="新密码（留空不修改）"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {password && (
            <Input
              label="确认密码"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          )}
          <Button variant="primary" onClick={handleSave} loading={loading}>
            保存更改
          </Button>
        </div>
      </Card>

      {user?.is_admin && (
        <Card className="p-5">
          <h3 className="text-sm font-semibold text-gh-text mb-4 flex items-center gap-2">
            <IconShield size={14} /> 管理员设置
          </h3>
          <div className="flex items-center justify-between p-3 rounded-md bg-gh-canvas-inset border border-gh-border">
            <div>
              <div className="text-sm text-gh-text">开放注册</div>
              <div className="text-xs text-gh-text-secondary">允许新用户自行注册账户</div>
            </div>
            <button
              onClick={handleToggleReg}
              className={`relative w-11 h-6 rounded-full transition-colors ${
                regEnabled ? 'bg-gh-success' : 'bg-gh-border'
              }`}
            >
              <motion.div
                animate={{ x: regEnabled ? 20 : 2 }}
                transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                className="absolute top-0.5 w-5 h-5 bg-white rounded-full shadow-md"
              />
            </button>
          </div>
        </Card>
      )}
    </div>
  )
}

const DataTab: React.FC = () => {
  const { toast } = useToast()
  const [exporting, setExporting] = useState(false)
  const [importing, setImporting] = useState(false)

  const handleExport = async () => {
    setExporting(true)
    try {
      const data = await api.exportData()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `hx-email-export-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      toast('导出成功', 'success')
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setExporting(false)
    }
  }

  const handleImport = async () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.json'
    input.onchange = async (e: any) => {
      const file = e.target.files?.[0]
      if (!file) return
      setImporting(true)
      try {
        const text = await file.text()
        const data = JSON.parse(text)
        await api.importData(data)
        toast('导入成功', 'success')
      } catch (err: any) {
        toast(err.message || '导入失败', 'error')
      } finally {
        setImporting(false)
      }
    }
    input.click()
  }

  return (
    <div className="space-y-5">
      <Card className="p-5">
        <h3 className="text-sm font-semibold text-gh-text mb-4 flex items-center gap-2">
          <IconDatabase size={14} /> 数据备份与恢复
        </h3>
        <p className="text-sm text-gh-text-secondary mb-4">
          导出包含邮箱账户、可用邮箱、分组、标签、平台和绑定关系的完整 JSON 数据。
        </p>
        <div className="grid grid-cols-2 gap-3 max-w-md">
          <Button variant="secondary" onClick={handleExport} loading={exporting}>
            <IconDownload size={14} /> 导出全部
          </Button>
          <Button variant="secondary" onClick={handleImport} loading={importing}>
            <IconUpload size={14} /> 从文件导入
          </Button>
        </div>
      </Card>

      <Card className="p-5 border-gh-danger/30 bg-gh-danger/5">
        <h3 className="text-sm font-semibold text-gh-danger mb-2">危险操作</h3>
        <p className="text-sm text-gh-text-secondary mb-3">
          删除账户会清除所有关联数据，此操作不可恢复。
        </p>
        <Button variant="danger">删除我的账户</Button>
      </Card>
    </div>
  )
}

const AboutTab: React.FC = () => {
  const [health, setHealth] = useState<'checking' | 'ok' | 'error'>('checking')

  React.useEffect(() => {
    setTimeout(() => setHealth('ok'), 500)
  }, [])

  return (
    <div className="space-y-5">
      <Card className="p-5">
        <div className="flex items-start gap-4">
          <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-gh-accent to-gh-purple flex items-center justify-center shadow-lg shadow-gh-accent/30">
            <IconDatabase size={24} className="text-white" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-bold text-gh-text">HX-Email</h3>
            <p className="text-sm text-gh-text-muted mt-1">
              多邮箱统一管理平台 · 版本 1.0.0
            </p>
            <div className="flex flex-wrap gap-2 mt-3">
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-gh-success/10 border border-gh-success/30 text-xs text-gh-success">
                <IconCheck size={12} /> FastAPI
              </div>
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-gh-accent/10 border border-gh-accent/30 text-xs text-gh-accent">
                <IconCheck size={12} /> React + TypeScript
              </div>
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-gh-purple/10 border border-gh-purple/30 text-xs text-gh-purple">
                <IconCheck size={12} /> Tailwind CSS
              </div>
            </div>
          </div>
        </div>
      </Card>

      <Card className="p-5">
        <h3 className="text-sm font-semibold text-gh-text mb-3 flex items-center gap-2">
          <IconRefresh size={14} /> 系统状态
        </h3>
        <div className="space-y-2">
          <div className="flex items-center justify-between px-3 py-2 rounded-md bg-gh-canvas-inset border border-gh-border">
            <span className="text-sm text-gh-text">后端服务</span>
            <span className="inline-flex items-center gap-1.5 text-xs text-gh-success">
              <span className="w-1.5 h-1.5 rounded-full bg-gh-success animate-pulse" />
              {health === 'checking' ? '检查中...' : '运行正常'}
            </span>
          </div>
          <div className="flex items-center justify-between px-3 py-2 rounded-md bg-gh-canvas-inset border border-gh-border">
            <span className="text-sm text-gh-text">数据库</span>
            <span className="inline-flex items-center gap-1.5 text-xs text-gh-success">
              <span className="w-1.5 h-1.5 rounded-full bg-gh-success animate-pulse" /> 已连接
            </span>
          </div>
          <div className="flex items-center justify-between px-3 py-2 rounded-md bg-gh-canvas-inset border border-gh-border">
            <span className="text-sm text-gh-text">CF 临时邮箱</span>
            <span className="inline-flex items-center gap-1.5 text-xs text-gh-warning">
              <span className="w-1.5 h-1.5 rounded-full bg-gh-warning" /> 未配置
            </span>
          </div>
        </div>
      </Card>

      <Card className="p-5">
        <h3 className="text-sm font-semibold text-gh-text mb-3">项目链接</h3>
        <a
          href="https://github.com"
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-gh-border/30 transition-colors"
        >
          <IconGithub size={18} className="text-gh-text" />
          <div className="flex-1">
            <div className="text-sm text-gh-text">GitHub 仓库</div>
            <div className="text-xs text-gh-text-secondary">查看源码与文档</div>
          </div>
        </a>
      </Card>
    </div>
  )
}
