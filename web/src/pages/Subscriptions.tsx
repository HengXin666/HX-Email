import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import {
  IconActivity,
  IconPause,
  IconPlay,
  IconPlus,
  IconRefresh,
  IconTrash,
} from "../components/icons";
import { Topbar } from "../components/layout";
import { Badge, Button, Card, Checkbox, Input, Select } from "../components/ui/Primitives";
import { useToast } from "../components/ui/Toast";
import type {
  RouterDirection,
  RouterEvent,
  RouterHubStats,
  RouterSource,
  RouterSubscription,
} from "../types/messaging";
import { SubscriptionIntegration } from "./impl/SubscriptionIntegration";
import { describeFilter, sourceChoices } from "./impl/subscription_snippets";

const MAX_LIVE = 50;

const message = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback;

/** Persistent subscriptions on the router hub: create, watch live, ack, integrate. */
export const Subscriptions: React.FC = () => {
  const { toast } = useToast();
  const [items, setItems] = useState<RouterSubscription[]>([]);
  const [sources, setSources] = useState<RouterSource[]>([]);
  const [stats, setStats] = useState<RouterHubStats | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [form, setForm] = useState({
    source: "",
    name: "",
    contains: "",
    direction: "inbound" as RouterDirection,
    mentionSelf: false,
    excludeSelf: true,
    earliest: false,
  });
  const [live, setLive] = useState<RouterEvent[]>([]);
  const [watching, setWatching] = useState(false);
  const [autoAck, setAutoAck] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

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
    return () => abortRef.current?.abort();
  }, [load]);

  const selected = items.find((item) => item.id === selectedId) ?? null;

  const stopWatching = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setWatching(false);
  };

  const startWatching = (id: number) => {
    stopWatching();
    const controller = new AbortController();
    abortRef.current = controller;
    setLive([]);
    setWatching(true);
    api
      .streamSubscription(
        id,
        (event) => setLive((prev) => [event, ...prev].slice(0, MAX_LIVE)),
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

  const create = async () => {
    if (!form.source.trim()) {
      toast("先填来源，例如 qq:1/group", "error");
      return;
    }
    try {
      const created = await api.createSubscription({
        source: form.source.trim(),
        name: form.name.trim(),
        from: form.earliest ? "earliest" : "now",
        filter: {
          direction: form.direction,
          contains: form.contains.trim(),
          mention_self: form.mentionSelf,
          exclude_self: form.excludeSelf,
        },
      });
      toast(`已创建订阅 #${created.id}`, "success");
      setSelectedId(created.id);
      await load();
    } catch (error) {
      toast(message(error, "创建失败"), "error");
    }
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
    if (!selected || live.length === 0) return;
    try {
      await api.ackSubscription(selected.id, live[0].cursor);
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
        subtitle="持久订阅 QQ / GitHub 消息，断线重连从确认位置续读"
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
          </div>

          <Card className="p-4 space-y-3">
            <h3 className="text-sm font-semibold text-gh-text">新建订阅</h3>
            {sources.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {sources.flatMap((src) =>
                  sourceChoices(src.platform, src.instance_id).map((choice) => (
                    <Badge
                      key={choice}
                      color={form.source === choice ? "#58a6ff" : "#8b949e"}
                      onClick={() => setForm({ ...form, source: choice })}
                    >
                      {src.name || src.platform} · {choice}
                    </Badge>
                  )),
                )}
              </div>
            )}
            <div className="grid md:grid-cols-3 gap-3">
              <Input
                label="来源 (会话或前缀)"
                placeholder="qq:1/group 或 github:2/repo/owner/name"
                value={form.source}
                onChange={(event) => setForm({ ...form, source: event.target.value })}
              />
              <Input
                label="名称"
                placeholder="例如 客服机器人"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
              <Input
                label="文本包含"
                placeholder="留空表示不过滤"
                value={form.contains}
                onChange={(event) => setForm({ ...form, contains: event.target.value })}
              />
            </div>
            <div className="flex flex-wrap items-end gap-4">
              <Select
                label="方向"
                value={form.direction}
                onChange={(value) => setForm({ ...form, direction: value as RouterDirection })}
                options={[
                  { value: "inbound", label: "入站" },
                  { value: "outbound", label: "出站" },
                  { value: "both", label: "双向" },
                ]}
                className="w-32"
              />
              <Checkbox
                label="排除自己发的"
                checked={form.excludeSelf}
                onChange={(checked) => setForm({ ...form, excludeSelf: checked })}
              />
              <Checkbox
                label="只要 @我"
                checked={form.mentionSelf}
                onChange={(checked) => setForm({ ...form, mentionSelf: checked })}
              />
              <Checkbox
                label="从最早的消息开始"
                checked={form.earliest}
                onChange={(checked) => setForm({ ...form, earliest: checked })}
              />
              <Button variant="primary" icon={<IconPlus size={14} />} onClick={create}>
                创建订阅
              </Button>
            </div>
          </Card>

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
                          {describeFilter(item.filter)}
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
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-gh-text flex-1">
                  实时事件 {selected ? `· #${selected.id}` : ""}
                </h3>
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
                <Button size="sm" variant="subtle" disabled={live.length === 0} onClick={ackLatest}>
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

          <SubscriptionIntegration selected={selected} />
        </div>
      </div>
    </div>
  );
};
