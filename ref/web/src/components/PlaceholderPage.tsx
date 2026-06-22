import React from 'react';
import { SidebarItem } from '../types';
import { OverviewIcon, PlatformsIcon, TempMailIcon, ApiIcon, SettingsIcon } from './Icons';

interface PlaceholderPageProps {
  item: SidebarItem;
}

const pageConfig: Record<string, { title: string; description: string; icon: React.FC<{ className?: string; size?: number }> }> = {
  overview: { title: '总览', description: '查看所有邮箱账号的概览信息，包括使用统计、最近活动等', icon: OverviewIcon },
  platforms: { title: '平台管理', description: '管理已接入的平台服务，配置邮箱绑定和通知策略', icon: PlatformsIcon },
  tempmail: { title: '临时邮箱', description: '创建一次性临时邮箱地址，用于注册和验证场景', icon: TempMailIcon },
  api: { title: 'API 接入', description: '管理 API 密钥，配置 Webhook 回调，查看接入文档', icon: ApiIcon },
  settings: { title: '设置', description: '配置系统参数、安全设置、通知偏好等', icon: SettingsIcon },
};

export const PlaceholderPage: React.FC<PlaceholderPageProps> = ({ item }) => {
  const config = pageConfig[item];
  if (!config) return null;

  const Icon = config.icon;

  return (
    <div className="flex-1 h-full bg-[#0d1117] flex items-center justify-center animate-fade-in">
      <div className="text-center max-w-md">
        <div className="w-16 h-16 bg-[#161b22] rounded-2xl flex items-center justify-center mx-auto mb-4 border border-[#21262d]">
          <Icon size={28} className="text-[#484f58]" />
        </div>
        <h2 className="text-[#f0f6fc] text-xl font-semibold mb-2">{config.title}</h2>
        <p className="text-[#8b949e] text-sm leading-relaxed">{config.description}</p>
        <div className="mt-6 inline-flex items-center gap-2 px-4 py-2 bg-[#161b22] rounded-lg border border-[#21262d]">
          <div className="w-2 h-2 rounded-full bg-[#d29922] animate-pulse" />
          <span className="text-[#8b949e] text-xs">功能开发中</span>
        </div>
      </div>
    </div>
  );
};
