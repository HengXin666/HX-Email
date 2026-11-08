import React, { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { IconKey, IconRefresh, IconZap } from "../../components/icons";
import { Badge, Button, Card, Input } from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import type {
  RouterSubscription,
  RouterWebhookDelivery,
  RouterWebhookPing,
  RouterWebhookStatus,
} from "../../types/messaging";
import { WEBHOOK_STATUS_LABEL } from "./subscription_snippets";

interface Props {
  subscription: RouterSubscription;
  onSecret: (secret: string) => void;
  onChanged: () => void;
}

const STATUS_COLOR: Record<RouterWebhookStatus, string> = {
  queued: "#58a6ff",
  sending: "#58a6ff",
  sent: "#3fb950",
  held: "#d29922",
  failed: "#f85149",
  dead: "#f85149",
};

const message = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback;

/** Webhook side of one subscription: target, test ping, secret rotation, delivery log. */
export const WebhookPanel: React.FC<Props> = ({ subscription, onSecret, onChanged }) => {
  const { toast } = useToast();
  const [url, setUrl] = useState(subscription.webhook?.url ?? "");
  const [deliveries, setDeliveries] = useState<RouterWebhookDelivery[]>([]);
  const [ping, setPing] = useState<RouterWebhookPing | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.listWebhookDeliveries(subscription.id);
      setDeliveries(data.deliveries);
    } catch (error) {
      toast(message(error, "读取投递记录失败"), "error");
    }
  }, [subscription.id, toast]);

  useEffect(() => {
    setUrl(subscription.webhook?.url ?? "");
    setPing(null);
    void load();
  }, [subscription.id, subscription.webhook?.url, load]);

  const saveUrl = async () => {
    try {
      await api.updateSubscription(subscription.id, { webhook_url: url.trim() });
      toast("已更新 Webhook 地址", "success");
      onChanged();
    } catch (error) {
      toast(message(error, "更新失败"), "error");
    }
  };

  const sendPing = async () => {
    try {
      setPing(await api.pingWebhook(subscription.id));
    } catch (error) {
      toast(message(error, "测试推送失败"), "error");
    }
  };

  const rotate = async () => {
    try {
      const rotated = await api.rotateWebhookSecret(subscription.id);
      if (rotated.webhook_secret) onSecret(rotated.webhook_secret);
      toast("已轮换密钥，旧密钥立即失效", "success");
    } catch (error) {
      toast(message(error, "轮换失败"), "error");
    }
  };

  const redeliver = async (deliveryId: string) => {
    try {
      await api.redeliverWebhook(subscription.id, deliveryId);
      toast(`已重新排队 ${deliveryId}`, "success");
      await load();
    } catch (error) {
      toast(message(error, "重投失败"), "error");
    }
  };

  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold text-gh-text flex-1" data-testid="webhook-panel">
          Webhook 推送 · #{subscription.id}
        </h3>
        <Button size="sm" variant="subtle" icon={<IconZap size={12} />} onClick={sendPing}>
          测试推送
        </Button>
        <Button size="sm" variant="ghost" icon={<IconKey size={12} />} onClick={rotate}>
          轮换密钥
        </Button>
        <Button size="sm" variant="ghost" icon={<IconRefresh size={12} />} onClick={load}>
          刷新
        </Button>
      </div>
      <p className="text-xs text-gh-text-secondary">
        每批最多 50 条，带 X-HX-Router-Signature (HMAC-SHA256) 与 X-HX-Router-Delivery；返回 2xx
        才推进确认位置，失败 10 秒起翻倍重试，24 小时后放弃。
      </p>
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <Input
            label="Webhook 地址"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
          />
        </div>
        <Button
          size="sm"
          disabled={!url.trim() || url.trim() === subscription.webhook?.url}
          onClick={saveUrl}
        >
          保存
        </Button>
      </div>
      {ping && (
        <div className="text-xs" data-testid="webhook-ping">
          <Badge color={ping.ok ? "#3fb950" : "#f85149"}>
            {ping.ok ? "接收端正常" : "接收端异常"}
          </Badge>{" "}
          {ping.status_code ? `HTTP ${ping.status_code} · ${ping.elapsed_ms} ms` : ping.error}
        </div>
      )}
      {deliveries.length === 0 ? (
        <p className="text-xs text-gh-text-secondary">还没有投递记录。</p>
      ) : (
        <ul className="divide-y divide-gh-border text-xs" data-testid="webhook-deliveries">
          {deliveries.map((item) => (
            <li key={item.delivery_id} className="py-1.5 flex items-center gap-2">
              <code className="font-mono text-gh-text">{item.delivery_id}</code>
              <Badge color={STATUS_COLOR[item.status] ?? "#8b949e"}>
                {WEBHOOK_STATUS_LABEL[item.status] ?? item.status}
              </Badge>
              <span className="text-gh-text-muted">
                {item.messages} 条 · 第 {item.attempts} 次
              </span>
              <span className="flex-1 truncate text-gh-text-muted" title={item.last_error}>
                {item.last_error}
              </span>
              {(item.status === "dead" || item.status === "failed") && (
                <Button size="sm" variant="subtle" onClick={() => redeliver(item.delivery_id)}>
                  重投
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
};
