import React, { useEffect, useState } from "react";
import { api } from "../../../api/client";
import {
  IconAlertTriangle,
  IconDatabase,
  IconRefresh,
  IconServer,
  IconUpload,
} from "../../../components/icons";
import { Button, Card, Input } from "../../../components/ui/Primitives";
import { SectionHeader, SettingsTabFrame } from "../SettingsControls";
import type { SettingsTabProps } from "../types";

interface SyncStatus {
  running: boolean;
  enabled: boolean;
  interval_seconds: number;
  last_run: string;
  next_run: string;
  last_error: string;
  last_summary: Record<string, unknown>;
}

interface StatusRowProps {
  icon: React.FC<{ size?: number; className?: string }>;
  label: string;
  value: string;
  color?: string;
}

const StatusRow: React.FC<StatusRowProps> = ({
  icon: Icon,
  label,
  value,
  color = "text-gh-text",
}) => (
  <div className="flex items-center justify-between rounded-md border border-gh-border bg-gh-canvas-inset px-3 py-2">
    <span className="flex items-center gap-2 text-sm text-gh-text">
      <Icon size={12} className="text-gh-text-muted" /> {label}
    </span>
    <span className={`text-xs ${color}`}>{value}</span>
  </div>
);

export const SyncSettingsTab: React.FC<SettingsTabProps> = ({ settings, setSetting, toast }) => {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);

  const refreshStatus = (): void => {
    void api
      .getSyncStatus()
      .then(setStatus)
      .catch(() => undefined);
  };

  useEffect(() => {
    refreshStatus();
    const timer = window.setInterval(refreshStatus, 5000);
    return () => window.clearInterval(timer);
  }, []);

  const handleSyncNow = async (): Promise<void> => {
    setIsSyncing(true);
    try {
      const report = await api.runSyncNow();
      if (report.error) {
        toast(`同步出错：${report.error}`, "error");
      } else {
        toast("同步完成", "success");
      }
      refreshStatus();
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "同步失败", "error");
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <SettingsTabFrame tabKey="sync">
      <Card className="p-5">
        <SectionHeader>主从同步配置</SectionHeader>
        <div className="max-w-lg space-y-3">
          <p className="text-xs text-gh-text-secondary">
            主从同步用于上下游备份：从主实例拉取快照 +
            将本地变更推回主实例（双向收敛，两端只增不删）。 配置后需点击右上角「保存设置」生效。
          </p>
          <Input
            label="主实例地址"
            value={settings.sync_url || ""}
            onChange={(event) => setSetting("sync_url", event.target.value)}
            placeholder="http://vps.example.com:8080"
          />
          <Input
            label="同步 Token"
            type="password"
            value={settings.sync_token || ""}
            onChange={(event) => setSetting("sync_token", event.target.value)}
            placeholder="主实例管理员 Bearer token"
          />
          <Input
            label="同步间隔 (秒)"
            type="number"
            min="0"
            max="86400"
            value={settings.sync_interval_seconds || "300"}
            onChange={(event) => setSetting("sync_interval_seconds", event.target.value)}
          />
          <p className="text-xs text-gh-text-secondary">
            间隔为 0 表示仅启动时同步一次；Token
            加密存储，环境变量中的初始值会在首次启动时自动写入设置。
          </p>
        </div>
      </Card>

      <Card className="p-5">
        <SectionHeader>同步状态</SectionHeader>
        <div className="max-w-md space-y-2">
          <StatusRow
            icon={IconServer}
            label="启用状态"
            value={status?.enabled ? "已启用" : "未配置"}
            color={status?.enabled ? "text-gh-success" : "text-gh-text-secondary"}
          />
          <StatusRow icon={IconRefresh} label="上次同步" value={status?.last_run || "从未同步"} />
          <StatusRow icon={IconDatabase} label="下次同步" value={status?.next_run || "—"} />
          {status?.last_error && (
            <div className="flex items-start gap-2 rounded-md border border-gh-danger/40 bg-gh-danger/10 px-3 py-2 text-xs text-gh-danger">
              <IconAlertTriangle size={14} className="mt-0.5 shrink-0" />
              <span className="break-all">{status.last_error}</span>
            </div>
          )}
          <Button
            variant="primary"
            size="sm"
            onClick={() => void handleSyncNow()}
            loading={isSyncing}
          >
            <IconUpload size={13} /> 立即同步
          </Button>
        </div>
      </Card>
    </SettingsTabFrame>
  );
};
