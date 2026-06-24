import React, { useEffect } from 'react'
import { motion } from 'framer-motion'
import { Topbar } from '../components/layout'
import { useApp } from '../store/AppContext'
import {
  IconMail,
  IconUser,
  IconServer,
  IconClock,
  IconDatabase,
  IconActivity,
  IconShield,
  IconZap,
  IconChevronRight
} from '../components/icons'
import { useNavigate } from 'react-router-dom'

interface StatCardProps {
  label: string
  value: number | string
  icon: React.FC<any>
  color: string
  trend?: string
  onClick?: () => void
}

const StatCard: React.FC<StatCardProps> = ({ label, value, icon: Icon, color, trend, onClick }) => (
  <motion.div
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    whileHover={{ y: -2 }}
    onClick={onClick}
    className={`relative overflow-hidden rounded-xl border border-gh-border bg-gh-canvas-subtle p-4 ${
      onClick ? 'cursor-pointer hover:border-gh-text-muted' : ''
    } transition-all`}
  >
    <div
      className="absolute top-0 right-0 w-24 h-24 rounded-full blur-2xl opacity-20"
      style={{ background: color }}
    />
    <div className="relative flex items-start justify-between">
      <div>
        <div className="text-xs text-gh-text-muted mb-1">{label}</div>
        <div className="text-2xl font-bold text-gh-text tabular-nums">{value}</div>
        {trend && <div className="text-xs text-gh-success mt-1">{trend}</div>}
      </div>
      <div
        className="w-9 h-9 rounded-lg flex items-center justify-center"
        style={{ background: color + '20', color }}
      >
        <Icon size={18} />
      </div>
    </div>
  </motion.div>
)

export const Overview: React.FC = () => {
  const { overview, emails, groups, platforms, refreshOverview } = useApp()
  const navigate = useNavigate()

  useEffect(() => {
    refreshOverview()
  }, [refreshOverview])

  const recentEmails = emails.slice(0, 5)
  const topPlatforms = platforms.slice(0, 5)

  return (
    <div className="flex-1 flex flex-col min-w-0">
      <Topbar title="工作台" subtitle="所有邮箱、平台、任务的总览视图" />

      <div className="flex-1 overflow-auto p-6">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="max-w-7xl mx-auto space-y-6"
        >
          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            <StatCard
              label="可用邮箱"
              value={overview?.usable_email_count ?? 0}
              icon={IconMail}
              color="#58a6ff"
              trend="↑ 活跃"
              onClick={() => navigate('/accounts')}
            />
            <StatCard
              label="邮箱账户"
              value={overview?.account_count ?? 0}
              icon={IconUser}
              color="#a371f7"
              onClick={() => navigate('/accounts')}
            />
            <StatCard
              label="平台"
              value={overview?.platform_count ?? 0}
              icon={IconServer}
              color="#3fb950"
              onClick={() => navigate('/platforms')}
            />
            <StatCard
              label="绑定关系"
              value={overview?.binding_count ?? 0}
              icon={IconActivity}
              color="#d29922"
            />
            <StatCard
              label="临时邮箱"
              value={overview?.temp_email_count ?? 0}
              icon={IconClock}
              color="#f0883e"
              onClick={() => navigate('/temp-mail')}
            />
            <StatCard
              label="邮箱池·可用"
              value={overview?.pool_available_count ?? 0}
              icon={IconDatabase}
              color="#db61a2"
            />
            <StatCard
              label="邮箱池·已领"
              value={overview?.pool_claimed_count ?? 0}
              icon={IconShield}
              color="#f85149"
            />
            <StatCard
              label="验证码记录"
              value={overview?.verification_count ?? 0}
              icon={IconZap}
              color="#6e7681"
            />
          </div>

          {/* Two columns */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* 最近邮箱 */}
            <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gh-text">最近更新的邮箱</h3>
                <button
                  onClick={() => navigate('/accounts')}
                  className="text-xs text-gh-accent hover:underline inline-flex items-center gap-0.5"
                >
                  查看全部 <IconChevronRight size={12} />
                </button>
              </div>
              <div className="space-y-1.5">
                {recentEmails.map((e, i) => (
                  <motion.div
                    key={e.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05 }}
                    className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-gh-border/30 transition-colors"
                  >
                    <div
                      className="w-8 h-8 rounded-md flex items-center justify-center text-xs font-semibold shrink-0"
                      style={{
                        background: (e.group?.color || '#58a6ff') + '20',
                        color: e.group?.color || '#58a6ff'
                      }}
                    >
                      {e.address.slice(0, 1).toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-gh-text truncate">{e.address}</div>
                      <div className="text-xs text-gh-text-secondary truncate">
                        {e.label || '—'} · {e.updated_at}
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>

            {/* 平台分布 */}
            <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-gh-text">平台分布</h3>
                <button
                  onClick={() => navigate('/platforms')}
                  className="text-xs text-gh-accent hover:underline inline-flex items-center gap-0.5"
                >
                  管理 <IconChevronRight size={12} />
                </button>
              </div>
              <div className="space-y-2">
                {topPlatforms.map((p, i) => {
                  const max = Math.max(...topPlatforms.map((x) => x.binding_count || 0), 1)
                  const pct = ((p.binding_count || 0) / max) * 100
                  return (
                    <motion.div
                      key={p.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.05 }}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm text-gh-text">{p.name}</span>
                        <span className="text-xs text-gh-text-muted tabular-nums">
                          {p.binding_count || 0} 绑定
                        </span>
                      </div>
                      <div className="h-1.5 bg-gh-canvas-inset rounded-full overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${pct}%` }}
                          transition={{ delay: 0.1 + i * 0.05, duration: 0.5 }}
                          className="h-full bg-gradient-to-r from-gh-accent to-gh-purple rounded-full"
                        />
                      </div>
                    </motion.div>
                  )
                })}
              </div>
            </div>
          </div>

          {/* 分组概览 */}
          <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle p-4">
            <h3 className="text-sm font-semibold text-gh-text mb-3">邮箱分组</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
              {groups.map((g, i) => (
                <motion.div
                  key={g.id}
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: i * 0.05 }}
                  whileHover={{ y: -2 }}
                  onClick={() => navigate('/accounts')}
                  className="cursor-pointer rounded-lg border border-gh-border bg-gh-canvas-inset p-3 hover:border-gh-text-muted transition-all"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <div
                      className="w-2.5 h-2.5 rounded-full"
                      style={{ background: g.color, boxShadow: `0 0 8px ${g.color}` }}
                    />
                    <span className="text-sm text-gh-text truncate">{g.name}</span>
                  </div>
                  <div className="text-2xl font-bold text-gh-text tabular-nums">
                    {g.count || 0}
                  </div>
                  <div className="text-xs text-gh-text-secondary">个邮箱</div>
                </motion.div>
              ))}
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  )
}
