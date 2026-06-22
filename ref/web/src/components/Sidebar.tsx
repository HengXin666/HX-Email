import React from 'react';
import { SidebarItem } from '../types';
import {
  OverviewIcon,
  AccountsIcon,
  PlatformsIcon,
  TempMailIcon,
  ApiIcon,
  SettingsIcon,
  LogoutIcon,
  GithubIcon,
} from './Icons';

interface SidebarProps {
  activeItem: SidebarItem;
  onItemClick: (item: SidebarItem) => void;
}

const navItems: { id: SidebarItem; label: string; icon: React.FC<{ className?: string; size?: number }> }[] = [
  { id: 'overview', label: '总览', icon: OverviewIcon },
  { id: 'accounts', label: '账号管理', icon: AccountsIcon },
  { id: 'platforms', label: '平台管理', icon: PlatformsIcon },
  { id: 'tempmail', label: '临时邮箱', icon: TempMailIcon },
  { id: 'api', label: 'API 接入', icon: ApiIcon },
  { id: 'settings', label: '设置', icon: SettingsIcon },
  { id: 'logout', label: '退出登录', icon: LogoutIcon },
];

export const Sidebar: React.FC<SidebarProps> = ({ activeItem, onItemClick }) => {
  return (
    <div className="w-[220px] min-w-[220px] h-screen bg-[#010409] border-r border-[#21262d] flex flex-col animate-slide-in-left">
      {/* Logo */}
      <div className="px-4 py-4 border-b border-[#21262d]">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-[#238636] rounded-md flex items-center justify-center">
            <span className="text-white font-bold text-sm">M</span>
          </div>
          <div>
            <div className="text-[#f0f6fc] font-semibold text-sm">MultiMail</div>
            <div className="text-[#484f58] text-xs">多邮箱管理</div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-2 px-2 overflow-y-auto">
        <div className="space-y-0.5">
          {navItems.map((item) => {
            const isActive = activeItem === item.id;
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                onClick={() => onItemClick(item.id)}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-all duration-200 group ${
                  isActive
                    ? 'bg-[#1f6feb1a] text-[#f0f6fc] font-medium'
                    : 'text-[#8b949e] hover:bg-[#161b22] hover:text-[#f0f6fc]'
                }`}
              >
                <Icon
                  className={`transition-colors duration-200 ${
                    isActive ? 'text-[#58a6ff]' : 'text-[#8b949e] group-hover:text-[#f0f6fc]'
                  }`}
                  size={18}
                />
                <span>{item.label}</span>
                {isActive && (
                  <div className="ml-auto w-1.5 h-1.5 rounded-full bg-[#58a6ff]" />
                )}
              </button>
            );
          })}
        </div>
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-[#21262d]">
        <a
          href="https://github.com"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-3 py-2 text-[#8b949e] hover:text-[#f0f6fc] rounded-md hover:bg-[#161b22] transition-all duration-200 text-sm"
        >
          <GithubIcon size={18} />
          <span>GitHub</span>
        </a>
      </div>
    </div>
  );
};
