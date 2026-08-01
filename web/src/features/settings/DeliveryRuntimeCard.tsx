import React, { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { IconActivity, IconDatabase, IconRefresh } from "../../components/icons";
import { Button, Card } from "../../components/ui/Primitives";

interface RuntimeStatus {
  polling: {
    running: boolean;
    enabled: boolean;
    interval_seconds: number;
    last_run: string;
    next_run: string;
    last_error: string;
  };
  deliveries: {
    pending: number;
    sending: number;
    sent: number;
    failed: number;
    skipped: number;
    last_error: string;
    last_error_at: string;
  };
  pool: {
    enabled: boolean;
    api_key_configured: boolean;
    total: number;
    available: number;
    claimed: number;
  };
}

interface StatusItemProps {
  label: string;
  value: string;
  tone?: "normal" | "success" | "danger";
}

const StatusItem: React.FC<StatusItemProps> = ({ label, value, tone = "normal" }) => {
  const toneClass: string =
    tone === "success" ? "text-gh-success" : tone === "danger" ? "text-gh-danger" : "text-gh-text";
  return (
    <div className="min-w-0 px-3 py-2.5 border-r last:border-r-0 border-gh-border">
      <div className="text-[11px] text-gh-text-muted">{label}</div>
      <div className={`mt-1 text-sm font-medium truncate ${toneClass}`}>{value}</div>
    </div>
  );
};

export const DeliveryRuntimeCard: React.FC = () => {
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const loadStatus = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    setError("");
    try {
      setStatus(await api.getRuntimeStatus());
    } catch (loadError: unknown) {
      setError(loadError instanceof Error ? loadError.message : "运行状态加载失败");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  const pollingTone: StatusItemProps["tone"] = status?.polling.enabled ? "success" : "normal";
  const deliveryTone: StatusItemProps["tone"] = status?.deliveries.failed ? "danger" : "success";
  const poolTone: StatusItemProps["tone"] = status?.pool.enabled ? "success" : "normal";

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div>
          <h4 className="text-xs font-semibold text-gh-text-muted uppercase tracking-wider">
            运行状态
          </h4>
          <p className="mt-1 text-xs text-gh-text-secondary">轮询、消息投递和外部邮箱池</p>
        </div>
        <Button variant="ghost" size="sm" onClick={loadStatus} loading={isLoading}>
          <IconRefresh size={13} /> 刷新
        </Button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 rounded-md border border-gh-border bg-gh-canvas-inset overflow-hidden">
        <StatusItem
          label="邮件轮询"
          value={
            status?.polling.enabled ? `运行中 · ${status.polling.interval_seconds}s` : "已暂停"
          }
          tone={pollingTone}
        />
        <StatusItem
          label="消息投递"
          value={
            status
              ? `${status.deliveries.sent} 已发送 · ${status.deliveries.failed} 失败`
              : "加载中"
          }
          tone={deliveryTone}
        />
        <StatusItem
          label="外部邮箱池"
          value={
            status?.pool.enabled ? `${status.pool.available}/${status.pool.total} 可领取` : "已关闭"
          }
          tone={poolTone}
        />
      </div>
      {(error || status?.polling.last_error || status?.deliveries.last_error) && (
        <div className="mt-3 flex items-start gap-2 text-xs text-gh-danger">
          <IconActivity size={13} className="mt-0.5 shrink-0" />
          <span>{error || status?.polling.last_error || status?.deliveries.last_error}</span>
        </div>
      )}
      {status?.pool.enabled && !status.pool.api_key_configured && (
        <div className="mt-3 flex items-center gap-2 text-xs text-gh-warning">
          <IconDatabase size={13} /> 请先在 API 安全中生成外部 API Key
        </div>
      )}
    </Card>
  );
};
