import { AnimatePresence, motion } from "framer-motion";
import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useApp } from "../store/AppContext";
import {
  IconActivity,
  IconBell,
  IconChevronRight,
  IconClock,
  IconCode,
  IconDatabase,
  IconGithub,
  IconInbox,
  IconKey,
  IconLogout,
  IconMail,
  IconServer,
  IconSettings,
  IconShield,
} from "./icons";
import { useToast } from "./ui/Toast";

const NAV = [
  { to: "/overview", label: "工作台", icon: IconInbox },
  { to: "/accounts", label: "可用邮箱", icon: IconMail },
  { to: "/account-stats", label: "账号统计", icon: IconActivity },
  { to: "/send-mail", label: "发送邮件", icon: IconMail },
  { to: "/platforms", label: "平台绑定", icon: IconServer },
  { to: "/temp-mail", label: "临时邮箱", icon: IconClock },
  { to: "/messaging", label: "消息插件", icon: IconBell },
  { to: "/token-tool", label: "OAuth Token", icon: IconKey },
  { to: "/refresh-log", label: "刷新日志", icon: IconClock },
  { to: "/pool-admin", label: "邮箱池", icon: IconDatabase },
  { to: "/audit", label: "审计日志", icon: IconShield },
  { to: "/api", label: "API 接入", icon: IconCode },
  { to: "/settings", label: "设置", icon: IconSettings },
];

export const Sidebar: React.FC = () => {
  const { user, logout } = useApp();
  const { toast } = useToast();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    toast("已退出登录", "success");
    navigate("/login");
  };

  return (
    <aside className="sticky top-0 flex h-screen w-16 shrink-0 flex-col border-r border-gh-border bg-gh-canvas-subtle/60 backdrop-blur-xl transition-all duration-200 md:w-[160px]">
      {/* Logo */}
      <div className="flex h-14 items-center justify-center gap-3 border-b border-gh-border px-3 md:justify-start md:px-5">
        <img
          src="/icon-512.png"
          alt="HX-Email"
          width="36"
          height="36"
          draggable={false}
          className="h-9 w-9 shrink-0 rounded-lg object-contain shadow-lg shadow-gh-accent/20"
        />
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="hidden flex-col leading-tight md:flex"
        >
          <span className="text-sm font-semibold gradient-text">HX-Email</span>
          <span className="text-[10px] text-gh-text-secondary">可用邮箱工作台</span>
        </motion.div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 md:px-3">
        <ul className="flex flex-col gap-0.5">
          {NAV.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                aria-label={item.label}
                title={item.label}
                className={({ isActive }) =>
                  `group relative flex items-center justify-center gap-3 rounded-md px-3 py-2 text-sm transition-colors md:justify-start ${
                    isActive
                      ? "bg-gh-accent/10 text-gh-accent"
                      : "text-gh-text-muted hover:text-gh-text hover:bg-gh-border/40"
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
                    <span className="hidden flex-1 md:block">{item.label}</span>
                    {isActive && (
                      <IconChevronRight size={14} className="hidden opacity-60 md:block" />
                    )}
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {/* User section */}
      <div className="border-t border-gh-border p-2 md:p-3">
        {user && (
          <div className="mb-2 hidden items-center gap-2 rounded-md bg-gh-border/20 px-3 py-2 md:flex">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-gh-purple to-gh-pink flex items-center justify-center text-xs font-semibold text-white">
              {user.username.slice(0, 1).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-gh-text truncate">{user.username}</div>
              <div className="text-[10px] text-gh-text-secondary">
                {user.is_admin ? "管理员" : "普通用户"}
              </div>
            </div>
          </div>
        )}
        <div className="flex flex-col gap-0.5">
          <button
            onClick={handleLogout}
            aria-label="退出登录"
            title="退出登录"
            className="flex items-center justify-center gap-3 rounded-md px-3 py-2 text-sm text-gh-text-muted transition-colors hover:bg-gh-danger/10 hover:text-gh-danger md:justify-start"
          >
            <IconLogout size={16} />
            <span className="hidden md:inline">退出登录</span>
          </button>
          <a
            href="https://github.com/HengXin666/HX-Email"
            target="_blank"
            rel="noreferrer"
            aria-label="GitHub"
            title="GitHub"
            className="flex items-center justify-center gap-3 rounded-md px-3 py-2 text-sm text-gh-text-muted transition-colors hover:bg-gh-border/40 hover:text-gh-text md:justify-start"
          >
            <IconGithub size={16} />
            <span className="hidden md:inline">GitHub</span>
          </a>
        </div>
      </div>
    </aside>
  );
};

export const Topbar: React.FC<{ title: string; subtitle?: string; actions?: React.ReactNode }> = ({
  title,
  subtitle,
  actions,
}) => (
  <div className="sticky top-0 z-30 flex min-h-14 items-center justify-between gap-3 border-b border-gh-border bg-gh-canvas/60 px-3 py-2 backdrop-blur-xl sm:px-6">
    <div className="min-w-0">
      <h1 className="text-base font-semibold text-gh-text">{title}</h1>
      {subtitle && (
        <div className="hidden truncate text-xs text-gh-text-secondary sm:block">{subtitle}</div>
      )}
    </div>
    {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
  </div>
);
