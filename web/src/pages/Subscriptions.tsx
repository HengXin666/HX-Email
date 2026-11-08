import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { SubscriptionSocket } from "../api/endpoints/router_hub";
import { IconActivity, IconPause, IconPlay, IconRefresh, IconTrash } from "../components/icons";
import { Topbar } from "../components/layout";
import { Badge, Button, Card, Checkbox, Select } from "../components/ui/Primitives";
import { useToast } from "../components/ui/Toast";
import type {
  RouterEvent,
  RouterHubStats,
  RouterSocketFrame,
  RouterSource,
  RouterSubscription,
} from "../types/messaging";
import { SubscriptionCreateForm } from "./impl/SubscriptionCreateForm";
import { SubscriptionIntegration } from "./impl/SubscriptionIntegration";
import { describeDelivery, describeFilter } from "./impl/subscription_snippets";
import { WebhookPanel } from "./impl/WebhookPanel";

const MAX_LIVE = 50;
type Transport = "sse" | "ws";

const message = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback;

const CLOSE_REASON: Record<number, string> = {
  4401: "WebSocket 未授权",
  4404: "订阅不存在",
  4409: "订阅已暂停",
};

/** Persistent subscriptions on the router hub: create, watch live, ack, push, integrate. */
export const Subscriptions: React.FC = () => {
  const { toast } = useToast();
  const [items, setItems] = useState<RouterSubscription[]>([]);
  const [sources, setSources] = useState<RouterSource[]>([]);
  const [stats, setStats] = useState<RouterHubStats | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [secret, setSecret] = useState<{ id: number; value: string } | null>(null);
  const [live, setLive] = useState<RouterEvent[]>([]);
  const [lastCursor, setLastCursor] = useState("");
  const [watching, setWatching] = useState(false);
  const [autoAck, setAutoAck] = useState(false);
  const [transport, setTransport] = useState<Transport>("ws");
  const abortRef = useRef<AbortController | null>(null);
  const socketRef = useRef<SubscriptionSocket | null>(null);

  const load = useCallback(async () => {
    try {
      const [subs, srcs, hub] = await Promise.all([
        api.listSubscriptions(),
        api.routerSources(),
        api.routerHubStats(),
      ]);
      setItems(subs.subscriptions);
      setSources(srcs.sources);
      setStats(hub);
    } catch (error) {
      toast(message(error, "读取订阅失败"), "error");
    }
  }, [toast]);

  useEffect(() => {
    void load();
    return () => {
      abortRef.current?.abort();
      socketRef.current?.close();
    };
  }, [load]);

  const selected = items.find((item) => item.id === selectedId) ?? null;

  const stopWatching = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    socketRef.current?.close();
    socketRef.current = null;
    setWatching(false);
  };

  const onFrame = (frame: RouterSocketFrame) => {
    if (frame.type === "messages") {
      setLive((prev) => [...[...frame.messages].reverse(), ...prev].slice(0, MAX_LIVE));
      setLastCursor(frame.next_cursor);
    } else if (frame.type === "acked") {
      toast("已确认到最新一条", "success");
      void load();
    } else if (frame.type === "error") {
      toast(frame.message || frame.code, "error");
    }
  };

  const watchSocket = (id: number) => {
    const socket = api.openSubscriptionSocket(
      id,
      onFrame,
      (code, reason) => {
        if (socketRef.current !== socket) return;
        socketRef.current = null;
        setWatching(false);
        if (code >= 4000) toast(CLOSE_REASON[code] ?? reason ?? "连接已关闭", "error");
      },
      autoAck,
    );
    socketRef.current = socket;
  };

  const watchSse = (id: number) => {
    const controller = new AbortController();
    abortRef.current = controller;
    api
      .streamSubscription(
        id,
        (event) => {
          setLive((prev) => [event, ...prev].slice(0, MAX_LIVE));
          setLastCursor(event.cursor);
        },
        controller.signal,
        autoAck,
      )
      .catch((error: unknown) => {
        if (!controller.signal.aborted) toast(message(error, "订阅流已断开"), "error");
      })
      .finally(() => {
        if (abortRef.current === controller) setWatching(false);
      });
  };

  const startWatching = (id: number) => {
    stopWatching();
    setLive([]);
    setLastCursor("");
    setWatching(true);
    if (transport === "ws") watchSocket(id);
    else watchSse(id);
  };

  const toggle = async (item: RouterSubscription) => {
    try {
      await api.updateSubscription(item.id, {
        status: item.status === "active" ? "paused" : "active",
      });
      if (item.id === selectedId) stopWatching();
      await load();
    } catch (error) {
      toast(message(error, "更新失败"), "error");
    }
  };

  const remove = async (item: RouterSubscription) => {
    try {
      await api.deleteSubscription(item.id);
      if (item.id === selectedId) {
        stopWatching();
        setSelectedId(null);
      }
      await load();
    } catch (error) {
      toast(message(error, "删除失败"), "error");
    }
  };

  const ackLatest = async () => {
    if (!selected || !lastCursor) return;
    if (socketRef.current) {
      socketRef.current.ack(lastCursor);
      return;
    }
    try {
      await api.ackSubscription(selected.id, lastCursor);
      toast("已确认到最新一条", "success");
      await load();
    } catch (error) {
      toast(message(error, "确认失败"), "error");
    }
  };

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
      <Topbar
        title="消息订阅"
        subtitle="持久订阅 QQ / GitHub 消息：长轮询、SSE、WebSocket 拉取，或 Webhook 推送"
        actions={
          <Button size="sm" icon={<IconRefresh size={12} />} onClick={() => void load()}>
            刷新
          </Button>
        }
      />
      <div className="flex-1 overflow-auto">
        <div className="max-w-6xl mx-auto p-6 space-y-5">
          <div
            className="flex flex-wrap gap-3 text-xs text-gh-text-secondary"
            data-testid="hub-stats"
          >
            <Badge color="#58a6ff">
              <IconActivity size={12} /> 正在等待 {stats?.waiting ?? 0}
            </Badge>
            <Badge color="#3fb950">已分发 {stats?.published ?? 0} 条</Badge>
            <Badge color="#a371f7">订阅 {items.length}</Badge>
            <Badge color="#d29922">Webhook {stats?.webhook_subscriptions ?? 0}</Badge>
          </div>

          <SubscriptionCreateForm
            sources={sources}
            onCreated={(created) => {
              setSelectedId(created.id);
              if (created.webhook_secret)
                setSecret({ id: created.id, value: created.webhook_secret });
              void load();
            }}
          />

          {secret && (
            <Card className="p-3 border-gh-success/40">
              <div className="flex items-center gap-2 text-xs">
                <span className="text-gh-text-secondary">
                  订阅 #{secret.id} 的 Webhook 密钥，只显示这一次：
                </span>
                <code
                  className="font-mono text-gh-text break-all flex-1"
                  data-testid="webhook-secret"
                >
                  {secret.value}
                </code>
                <Button size="sm" variant="ghost" onClick={() => setSecret(null)}>
                  我已保存
                </Button>
              </div>
            </Card>
          )}

          <div className="grid lg:grid-cols-2 gap-5">
            <Card className="p-0 overflow-hidden">
              {items.length === 0 ? (
                <p className="p-6 text-sm text-gh-text-secondary">还没有订阅。</p>
              ) : (
                <ul className="divide-y divide-gh-border">
                  {items.map((item) => (
                    <li
                      key={item.id}
                      className={`p-3 ${item.id === selectedId ? "bg-gh-accent/5" : ""}`}
                    >
                      <button
                        type="button"
                        className="w-full text-left"
                        onClick={() => setSelectedId(item.id)}
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-gh-text">
                            #{item.id} {item.name || "未命名"}
                          </span>
                          <Badge color={item.status === "active" ? "#3fb950" : "#d29922"}>
                            {item.status === "active" ? "运行中" : "已暂停"}
                          </Badge>
                          {item.delivery === "webhook" && <Badge color="#d29922">Webhook</Badge>}
                          <span className="flex-1" />
                          <Badge color="#58a6ff">
                            积压 {item.backlog ?? 0}
                            {item.backlog_capped ? "+" : ""}
                          </Badge>
                        </div>
                        <code className="block text-xs font-mono text-gh-text-secondary mt-1">
                          {item.address || item.source}
                        </code>
                        <div className="text-xs text-gh-text-muted mt-1">
                          {describeFilter(item.filter)} · {describeDelivery(item)}
                        </div>
                      </button>
                      <div className="flex gap-2 mt-2">
                        <Button
                          size="sm"
                          variant="subtle"
                          icon={<IconActivity size={12} />}
                          disabled={item.status !== "active"}
                          onClick={() => {
                            setSelectedId(item.id);
                            startWatching(item.id);
                          }}
                        >
                          实时查看
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={
                            item.status === "active" ? (
                              <IconPause size={12} />
                            ) : (
                              <IconPlay size={12} />
                            )
                          }
                          onClick={() => toggle(item)}
                        >
                          {item.status === "active" ? "暂停" : "恢复"}
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          icon={<IconTrash size={12} />}
                          onClick={() => remove(item)}
                        >
                          删除
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card className="p-4 space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold text-gh-text flex-1">
                  实时事件 {selected ? `· #${selected.id}` : ""}
                </h3>
                <Select
                  value={transport}
                  onChange={(value) => {
                    stopWatching();
                    setTransport(value as Transport);
                  }}
                  options={[
                    { value: "ws", label: "WebSocket" },
                    { value: "sse", label: "SSE" },
                  ]}
                  className="w-32"
                />
                <Checkbox label="推出即确认" checked={autoAck} onChange={setAutoAck} />
                {watching ? (
                  <Button size="sm" onClick={stopWatching}>
                    停止
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    disabled={!selected || selected.status !== "active"}
                    onClick={() => selected && startWatching(selected.id)}
                  >
                    开始
                  </Button>
                )}
                <Button size="sm" variant="subtle" disabled={!lastCursor} onClick={ackLatest}>
                  确认到最新
                </Button>
              </div>
              {live.length === 0 ? (
                <p className="text-xs text-gh-text-secondary">
                  {watching ? "已连接，等待新消息…" : "选一个订阅点“实时查看”。"}
                </p>
              ) : (
                <ul className="space-y-2 max-h-96 overflow-auto" data-testid="live-events">
                  {live.map((event) => (
                    <li key={event.cursor} className="rounded-md border border-gh-border p-2">
                      <div className="flex gap-2 text-[11px] text-gh-text-muted">
                        <span>{event.kind || event.platform}</span>
                        <code className="font-mono truncate flex-1">
                          {event.address || event.session}
                        </code>
                        <span>{event.occurred_at}</span>
                      </div>
                      <div className="text-sm text-gh-text mt-1 break-words">
                        <span className="text-gh-accent">
                          {event.sender.name || event.sender.id}
                        </span>
                        ：{event.text}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          {selected?.delivery === "webhook" && (
            <WebhookPanel
              subscription={selected}
              onSecret={(value) => setSecret({ id: selected.id, value })}
              onChanged={() => void load()}
            />
          )}

          <SubscriptionIntegration
            selected={selected}
            webhookSecret={secret && secret.id === selected?.id ? secret.value : ""}
          />
        </div>
      </div>
    </div>
  );
};
