import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import {
  IconCheck,
  IconDatabase,
  IconMail,
  IconRefresh,
  IconSettings,
  IconShield,
  IconUser,
  IconZap,
} from "../components/icons";
import { Topbar } from "../components/layout";
import { Button } from "../components/ui/Primitives";
import { useToast } from "../components/ui/Toast";
import { AutomationSettingsTab } from "../features/settings/automation/AutomationSettingsTab";
import { ApiSecuritySettingsTab } from "../features/settings/tabs/ApiSecuritySettingsTab";
import { BasicSettingsTab } from "../features/settings/tabs/BasicSettingsTab";
import { SyncSettingsTab } from "../features/settings/tabs/SyncSettingsTab";
import { TempMailSettingsTab } from "../features/settings/tabs/TempMailSettingsTab";
import { UserManagementSettingsTab } from "../features/settings/tabs/UserManagementSettingsTab";

import type { SettingsTabProps } from "../features/settings/types";
import { useApp } from "../store/AppContext";

type SettingsTab = "basic" | "tempmail" | "apisecurity" | "automation" | "sync" | "users";

const ADMIN_TABS = [
  { key: "tempmail", label: "临时邮箱", icon: IconMail },
  { key: "apisecurity", label: "API 安全", icon: IconShield },
  { key: "automation", label: "自动化", icon: IconZap },
  { key: "sync", label: "主从同步", icon: IconDatabase },
  { key: "users", label: "用户管理", icon: IconUser },
] as const;

export const Settings: React.FC = () => {
  const { user, accounts } = useApp();
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<SettingsTab>("basic");
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(Boolean(user?.is_admin));
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!user?.is_admin) {
      setIsLoading(false);
      return;
    }
    api
      .getSettings()
      .then(setSettings)
      .catch((error: unknown) =>
        toast(error instanceof Error ? error.message : "设置加载失败", "error"),
      )
      .finally(() => setIsLoading(false));
  }, [toast, user?.is_admin]);

  const setSetting = useCallback((key: string, value: string): void => {
    setSettings((current) => ({ ...current, [key]: value }));
  }, []);

  const handleSave = async (): Promise<void> => {
    setIsSaving(true);
    try {
      const savedSettings = await api.updateSettings(settings);
      setSettings(savedSettings);
      toast("设置已保存", "success");
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "设置保存失败", "error");
    } finally {
      setIsSaving(false);
    }
  };

  const tabs = [
    { key: "basic", label: "基础", icon: IconSettings },
    ...(user?.is_admin ? ADMIN_TABS : []),
  ] as const;
  const tabProps: SettingsTabProps = { settings, setSetting, toast, user, accounts };

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <Topbar
        title="系统设置"
        subtitle="配置邮箱服务、通知与自动化"
        actions={
          user?.is_admin ? (
            <Button variant="primary" onClick={handleSave} loading={isSaving} disabled={isLoading}>
              <IconCheck size={14} /> 保存设置
            </Button>
          ) : undefined
        }
      />

      <div className="flex-1 overflow-auto">
        <div className="mx-auto max-w-3xl p-4 sm:p-6">
          <div className="mb-5 flex items-center gap-1 overflow-x-auto border-b border-gh-border">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                className={`relative flex shrink-0 items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors ${
                  activeTab === tab.key ? "text-gh-accent" : "text-gh-text-muted hover:text-gh-text"
                }`}
              >
                <tab.icon size={13} />
                {tab.label}
                {activeTab === tab.key && (
                  <motion.div
                    layoutId="settings-tab-underline"
                    className="absolute bottom-0 left-0 right-0 h-0.5 rounded-full bg-gh-accent"
                  />
                )}
              </button>
            ))}
          </div>

          {isLoading ? (
            <div className="flex items-center justify-center py-20 text-sm text-gh-text-secondary">
              <IconRefresh size={16} className="mr-2 animate-spin" /> 加载中...
            </div>
          ) : (
            <AnimatePresence mode="wait">
              {activeTab === "basic" && <BasicSettingsTab {...tabProps} />}
              {activeTab === "tempmail" && user?.is_admin && <TempMailSettingsTab {...tabProps} />}
              {activeTab === "apisecurity" && user?.is_admin && (
                <ApiSecuritySettingsTab {...tabProps} />
              )}
              {activeTab === "automation" && user?.is_admin && (
                <AutomationSettingsTab {...tabProps} />
              )}
              {activeTab === "sync" && user?.is_admin && <SyncSettingsTab {...tabProps} />}
              {activeTab === "users" && user?.is_admin && (
                <UserManagementSettingsTab {...tabProps} />
              )}
            </AnimatePresence>
          )}
        </div>
      </div>
    </div>
  );
};
