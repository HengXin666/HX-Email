import React, { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  IconInbox,
  IconUser,
  IconServer,
  IconClock,
  IconCode,
  IconSettings,
  IconLogout,
  IconGithub,
  IconChevronRight
} from './icons'
import { useApp } from '../store/AppContext'
import { useToast } from './ui/Toast'

const NAV = [
  { to: '/overview', label: '总览', icon: IconInbox },
  { to: '/accounts', label: '账号管理', icon: IconUser },
  { to: '/platforms', label: '平台管理', icon: IconServer },
  { to: '/temp-mail', label: '临时邮箱', icon: IconClock },
  { to: '/api', label: 'API 接入', icon: IconCode },
  { to: '/settings', label: '设置', icon: IconSettings }
]

export const Sidebar: React.FC = () => {
  const { user, logout } = useApp()
  const { toast } = useToast()
  const navigate = useNavigate()
  const [collapsed] = useState(false)

  const handleLogout = async () => {
    await logout()
    toast('已退出登录', 'success')
    navigate('/login')
  }

  return (
    <aside
      className={`${
        collapsed ? 'w-16' : 'w-60'
      } shrink-0 h-screen sticky top-0 border-r border-gh-border bg-gh-canvas-subtle/60 backdrop-blur-xl flex flex-col transition-all duration-200`}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 h-14 border-b border-gh-border">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-gh-accent to-gh-purple flex items-center justify-center shadow-lg shadow-gh-accent/20">
          <IconInbox size={16} className="text-white" />
        </div>
        {!collapsed && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col leading-tight"
          >
            <span className="font-semibold text-sm gradient-text">HX-Email</span>
            <span className="text-[10px] text-gh-text-secondary">多邮箱管理平台</span>
          </motion.div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-3 overflow-y-auto">
        <ul className="flex flex-col gap-0.5">
          {NAV.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) =>
                  `group relative flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                    isActive
                      ? 'bg-gh-accent/10 text-gh-accent'
                      : 'text-gh-text-muted hover:text-gh-text hover:bg-gh-border/40'
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <motion.div
                        layoutId="sidebar-indicator"
                        className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-gh-accent rounded-full"
                      />
                    )}
                    <item.icon size={16} />
                    {!collapsed && <span className="flex-1">{item.label}</span>}
                    {!collapsed && isActive && (
                      <IconChevronRight size={14} className="opacity-60" />
                    )}
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {/* User section */}
      <div className="p-3 border-t border-gh-border">
        {!collapsed && user && (
          <div className="flex items-center gap-2 px-3 py-2 mb-2 rounded-md bg-gh-border/20">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-gh-purple to-gh-pink flex items-center justify-center text-xs font-semibold text-white">
              {user.username.slice(0, 1).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-gh-text truncate">{user.username}</div>
              <div className="text-[10px] text-gh-text-secondary">
                {user.is_admin ? '管理员' : '普通用户'}
              </div>
            </div>
          </div>
        )}
        <div className="flex flex-col gap-0.5">
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 px-3 py-2 rounded-md text-sm text-gh-text-muted hover:text-gh-danger hover:bg-gh-danger/10 transition-colors"
          >
            <IconLogout size={16} />
            {!collapsed && <span>退出登录</span>}
          </button>
          <a
            href="https://github.com"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-3 px-3 py-2 rounded-md text-sm text-gh-text-muted hover:text-gh-text hover:bg-gh-border/40 transition-colors"
          >
            <IconGithub size={16} />
            {!collapsed && <span>GitHub</span>}
          </a>
        </div>
      </div>
    </aside>
  )
}

export const Topbar: React.FC<{ title: string; subtitle?: string; actions?: React.ReactNode }> = ({
  title,
  subtitle,
  actions
}) => (
  <div className="flex items-center justify-between h-14 px-6 border-b border-gh-border bg-gh-canvas/60 backdrop-blur-xl sticky top-0 z-30">
    <div>
      <h1 className="text-base font-semibold text-gh-text">{title}</h1>
      {subtitle && <div className="text-xs text-gh-text-secondary">{subtitle}</div>}
    </div>
    {actions && <div className="flex items-center gap-2">{actions}</div>}
  </div>
)
