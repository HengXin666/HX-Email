import type React from "react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../../api/client";
import { IconRefresh } from "../../../components/icons";
import { Button, Card } from "../../../components/ui/Primitives";
import { SectionHeader, SettingsTabFrame, SettingsToggle } from "../SettingsControls";
import type { SettingsTabProps } from "../types";
import { InstanceBackupCard } from "./InstanceBackupCard";

interface AdminUserSummary {
  id: number;
  username: string;
  is_admin: boolean;
  email_account_count: number;
  usable_email_count: number;
}

export const UserManagementSettingsTab: React.FC<SettingsTabProps> = ({ toast, user }) => {
  const [users, setUsers] = useState<AdminUserSummary[]>([]);
  const [isRegistrationEnabled, setIsRegistrationEnabled] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSavingRegistration, setIsSavingRegistration] = useState(false);

  const loadUsers = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    try {
      const [registration, userRows] = await Promise.all([
        api.getRegistrationSetting(),
        api.listAdminUsers(),
      ]);
      setIsRegistrationEnabled(registration.registration_enabled);
      setUsers(userRows);
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "加载用户管理数据失败", "error");
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (user?.is_admin) void loadUsers();
  }, [loadUsers, user?.is_admin]);

  const handleRegistrationChange = async (isEnabled: boolean): Promise<void> => {
    setIsSavingRegistration(true);
    try {
      const result = await api.updateRegistrationSetting(isEnabled);
      setIsRegistrationEnabled(result.registration_enabled);
      toast(result.registration_enabled ? "已开启系统注册" : "已关闭系统注册", "success");
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "更新注册开关失败", "error");
    } finally {
      setIsSavingRegistration(false);
    }
  };

  if (!user?.is_admin) return null;

  return (
    <SettingsTabFrame tabKey="users">
      <Card className="p-5">
        <SectionHeader>系统注册</SectionHeader>
        <div className="flex items-center justify-between gap-4 rounded-md border border-gh-border bg-gh-canvas-inset p-3">
          <div>
            <div className="text-sm text-gh-text">允许新用户注册</div>
            <div className="text-xs text-gh-text-secondary">关闭后仅已有用户可以登录</div>
          </div>
          <SettingsToggle
            enabled={isRegistrationEnabled}
            onChange={(value) => void handleRegistrationChange(value)}
            disabled={isLoading || isSavingRegistration}
          />
        </div>
      </Card>

      <InstanceBackupCard toast={toast} />

      <Card className="overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-gh-border px-5 py-4">
          <div>
            <SectionHeader>注册用户</SectionHeader>
            <div className="-mt-2 text-xs text-gh-text-secondary">账号和邮箱资源概览</div>
          </div>
          <Button variant="secondary" size="sm" onClick={loadUsers} loading={isLoading}>
            <IconRefresh size={13} /> 刷新
          </Button>
        </div>

        {isLoading ? (
          <div className="py-10 text-center text-sm text-gh-text-secondary">
            <IconRefresh size={16} className="mr-2 inline animate-spin" /> 加载中...
          </div>
        ) : users.length === 0 ? (
          <div className="py-10 text-center text-sm text-gh-text-secondary">暂无用户</div>
        ) : (
          <div className="overflow-x-auto">
            <div className="min-w-[640px]">
              <div className="grid grid-cols-[70px_minmax(180px,1fr)_100px_110px_110px] gap-3 border-b border-gh-border bg-gh-canvas-inset px-5 py-2.5 text-xs font-semibold uppercase tracking-wider text-gh-text-muted">
                <div>ID</div>
                <div>用户名</div>
                <div className="text-center">角色</div>
                <div className="text-center">邮箱账号</div>
                <div className="text-center">可用邮箱</div>
              </div>
              <div className="divide-y divide-gh-border/50">
                {users.map((item) => (
                  <div
                    key={item.id}
                    className="grid grid-cols-[70px_minmax(180px,1fr)_100px_110px_110px] items-center gap-3 px-5 py-3 text-sm transition-colors hover:bg-gh-border/20"
                  >
                    <div className="text-xs tabular-nums text-gh-text-secondary">#{item.id}</div>
                    <div className="flex min-w-0 items-center gap-2">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gh-accent/20 text-xs font-semibold text-gh-accent">
                        {item.username.slice(0, 1).toUpperCase()}
                      </div>
                      <span className="truncate text-gh-text">{item.username}</span>
                    </div>
                    <div className="text-center text-xs text-gh-text-secondary">
                      {item.is_admin ? "管理员" : "普通用户"}
                    </div>
                    <div className="text-center text-gh-text">{item.email_account_count}</div>
                    <div className="text-center text-gh-text">{item.usable_email_count}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </Card>
    </SettingsTabFrame>
  );
};
