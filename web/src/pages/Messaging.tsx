import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { IconBell, IconLink, IconPlus, IconRefresh, IconTrash, IconZap } from "../components/icons";
import { Topbar } from "../components/layout";
import { Badge, Button, Card, Input } from "../components/ui/Primitives";
import { EmptyState, LoadingState } from "../components/ui/StateDisplay";
import { useToast } from "../components/ui/Toast";
import type {
  MessagingConversation,
  MessagingGroup,
  MessagingInstance,
  MessagingMessage,
  MessagingPluginInfo,
} from "../types";

const STATUS_COLORS: Record<string, string> = {
  stopped: "#6e7681",
  connecting: "#d29922",
  online: "#3fb950",
  error: "#f85149",
};

const STATUS_LABELS: Record<string, string> = {
  stopped: "未连接",
  connecting: "连接中",
  online: "在线",
  error: "错误",
};

function statusColor(status: string): string {
  return STATUS_COLORS[status] ?? "#6e7681";
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export const Messaging: React.FC = () => {
  const { toast } = useToast();
  const [plugins, setPlugins] = useState<MessagingPluginInfo[]>([]);
  const [instances, setInstances] = useState<MessagingInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [conversations, setConversations] = useState<MessagingConversation[]>([]);
  const [groups, setGroups] = useState<MessagingGroup[]>([]);
  const [messages, setMessages] = useState<MessagingMessage[]>([]);
  const [activeChat, setActiveChat] = useState<MessagingConversation | null>(null);
  const [sendText, setSendText] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: "", api_base_url: "", webui_url: "", event_token: "" });
  const [busy, setBusy] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [pluginList, instanceList] = await Promise.all([api.catalog(), api.listInstances()]);
      setPlugins(pluginList);
      setInstances(instanceList);
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "加载失败", "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const openInstance = useCallback(
    async (instance: MessagingInstance) => {
      setSelectedId(instance.id);
      setActiveChat(null);
      setMessages([]);
      try {
        const [conversationList, groupList] = await Promise.all([
          api.conversations(instance.id),
          api.groups(instance.id),
        ]);
        setConversations(conversationList);
        setGroups(groupList);
      } catch (error: unknown) {
        toast(error instanceof Error ? error.message : "加载会话失败", "error");
      }
    },
    [toast],
  );

  const selectConversation = useCallback(
    async (conversation: MessagingConversation) => {
      if (selectedId === null) return;
      setActiveChat(conversation);
      try {
        setMessages(await api.messages(selectedId, conversation.chat_id, 50));
      } catch (error: unknown) {
        toast(error instanceof Error ? error.message : "加载消息失败", "error");
      }
    },
    [selectedId, toast],
  );

  const handleSend = useCallback(async () => {
    if (selectedId === null || activeChat === null || !sendText.trim()) return;
    setBusy("send");
    try {
      await api.sendMessage(selectedId, {
        chat_id: activeChat.chat_id,
        chat_type: activeChat.chat_type,
        text: sendText.trim(),
      });
      setSendText("");
      setMessages(await api.messages(selectedId, activeChat.chat_id, 50));
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "发送失败", "error");
    } finally {
      setBusy(null);
    }
  }, [activeChat, selectedId, sendText, toast]);

  const handleConnect = useCallback(
    async (instance: MessagingInstance) => {
      setBusy(`connect-${instance.id}`);
      try {
        await api.connect(instance.id);
        toast("已连接", "success");
        await loadAll();
      } catch (error: unknown) {
        toast(error instanceof Error ? error.message : "连接失败", "error");
      } finally {
        setBusy(null);
      }
    },
    [loadAll, toast],
  );

  const handleDisconnect = useCallback(
    async (instance: MessagingInstance) => {
      setBusy(`disconnect-${instance.id}`);
      try {
        await api.disconnect(instance.id);
        toast("已断开", "success");
        await loadAll();
      } catch (error: unknown) {
        toast(error instanceof Error ? error.message : "断开失败", "error");
      } finally {
        setBusy(null);
      }
    },
    [loadAll, toast],
  );

  const handleLogin = useCallback(
    async (instance: MessagingInstance) => {
      try {
        const ticket = await api.getLogin(instance.id);
        if (ticket.url) {
          window.open(ticket.url, "_blank", "noopener,noreferrer");
        }
        toast(ticket.instructions || "请在打开的页面中扫码登录", "success");
      } catch (error: unknown) {
        toast(error instanceof Error ? error.message : "获取登录引导失败", "error");
      }
    },
    [toast],
  );

  const handleDelete = useCallback(
    async (instance: MessagingInstance) => {
      if (!window.confirm(`确认删除实例「${instance.name}」？`)) return;
      try {
        await api.deleteInstance(instance.id);
        if (selectedId === instance.id) {
          setSelectedId(null);
          setConversations([]);
          setGroups([]);
          setMessages([]);
        }
        toast("已删除", "success");
        await loadAll();
      } catch (error: unknown) {
        toast(error instanceof Error ? error.message : "删除失败", "error");
      }
    },
    [loadAll, selectedId, toast],
  );

  const handleCreate = useCallback(async () => {
    setBusy("create");
    try {
      await api.createInstance({
        kind: "qq",
        name: form.name.trim() || "QQ 机器人",
        config: {
          api_base_url: form.api_base_url.trim(),
          webui_url: form.webui_url.trim(),
          event_token: form.event_token.trim(),
        },
      });
      setShowCreate(false);
      setForm({ name: "", api_base_url: "", webui_url: "", event_token: "" });
      toast("实例已创建，请配置 NapCat 事件推送后连接", "success");
      await loadAll();
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "创建失败", "error");
    } finally {
      setBusy(null);
    }
  }, [form, loadAll, toast]);

  const handleGroupAction = useCallback(
    async (group: MessagingGroup, action: string) => {
      const memberId = window.prompt(
        action === "kick" ? `输入要踢出群 ${group.name} 的 QQ 号` : `输入要禁言（分钟）的 QQ 号`,
      );
      if (!memberId) return;
      try {
        await api.groupAction(selectedId ?? 0, group.group_id, {
          action,
          member_id: memberId,
          duration_seconds: action === "ban" ? 10 : 0,
        });
        toast("操作成功", "success");
      } catch (error: unknown) {
        toast(error instanceof Error ? error.message : "操作失败", "error");
      }
    },
    [selectedId, toast],
  );

  const selectedInstance = instances.find((item) => item.id === selectedId) ?? null;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <Topbar
        title="消息插件"
        subtitle="以插件方式接入 QQ / 微信 / Telegram / Discord，像收邮件一样收发消息"
        actions={
          <Button
            variant="primary"
            size="sm"
            icon={<IconPlus size={14} />}
            onClick={() => setShowCreate(true)}
          >
            添加 QQ 实例
          </Button>
        }
      />

      {loading ? (
        <LoadingState message="加载消息插件..." />
      ) : (
        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {plugins.map((plugin) => (
              <Card key={plugin.key} className="flex flex-col gap-2 p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm font-semibold text-gh-text">
                    <IconBell size={16} className="text-gh-accent" />
                    {plugin.display_name}
                  </div>
                  <Badge color={plugin.available ? "#3fb950" : "#6e7681"}>
                    {plugin.available ? "可用" : "规划中"}
                  </Badge>
                </div>
                <p className="text-xs leading-relaxed text-gh-text-secondary">
                  {plugin.description}
                </p>
                {plugin.capabilities.risk_notice && (
                  <p className="text-xs leading-relaxed text-gh-danger/80">
                    {plugin.capabilities.risk_notice}
                  </p>
                )}
              </Card>
            ))}
          </div>

          <h2 className="mt-6 mb-2 text-sm font-semibold text-gh-text">我的实例</h2>
          {instances.length === 0 ? (
            <EmptyState message="还没有消息实例，点击右上角添加" />
          ) : (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {instances.map((instance) => (
                <Card
                  key={instance.id}
                  selected={selectedId === instance.id}
                  onClick={() => openInstance(instance)}
                  className="p-4"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 text-sm font-semibold text-gh-text">
                        <span className="truncate">{instance.name}</span>
                        <Badge color={statusColor(instance.status)}>
                          {statusLabel(instance.status)}
                        </Badge>
                      </div>
                      <div className="mt-1 text-xs text-gh-text-secondary">
                        {instance.kind.toUpperCase()} ·{" "}
                        {instance.config.api_base_url || "未配置 API"}
                      </div>
                    </div>
                    <div className="flex shrink-0 gap-1">
                      {instance.status === "online" ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleDisconnect(instance)}
                        >
                          断开
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          loading={busy === `connect-${instance.id}`}
                          onClick={() => handleConnect(instance)}
                        >
                          连接
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<IconLink size={14} />}
                        onClick={() => handleLogin(instance)}
                      >
                        扫码
                      </Button>
                      <Button
                        size="sm"
                        variant="danger"
                        icon={<IconTrash size={14} />}
                        onClick={() => handleDelete(instance)}
                      />
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}

          {selectedInstance && (
            <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
              <Card className="p-4">
                <h3 className="mb-2 text-sm font-semibold text-gh-text">会话</h3>
                <div className="max-h-80 space-y-1 overflow-y-auto">
                  {conversations.length === 0 ? (
                    <EmptyState message="无会话（需先连接并登录）" />
                  ) : (
                    conversations.map((conversation) => (
                      <button
                        key={`${conversation.chat_type}-${conversation.chat_id}`}
                        type="button"
                        onClick={() => selectConversation(conversation)}
                        className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-xs transition-colors ${
                          activeChat?.chat_id === conversation.chat_id
                            ? "bg-gh-accent/10 text-gh-accent"
                            : "text-gh-text hover:bg-gh-border/40"
                        }`}
                      >
                        <span className="truncate">
                          {conversation.name || conversation.chat_id}
                        </span>
                        <Badge color={conversation.chat_type === "group" ? "#a371f7" : "#58a6ff"}>
                          {conversation.chat_type === "group" ? "群" : "私聊"}
                        </Badge>
                      </button>
                    ))
                  )}
                </div>
              </Card>

              <Card className="flex flex-col p-4">
                <h3 className="mb-2 text-sm font-semibold text-gh-text">
                  {activeChat ? activeChat.name || activeChat.chat_id : "消息"}
                </h3>
                <div className="flex-1 space-y-2 overflow-y-auto">
                  {messages.length === 0 ? (
                    <EmptyState message="选择会话查看消息" />
                  ) : (
                    messages.map((message) => (
                      <div
                        key={`${message.message_id}-${message.created_at}`}
                        className={`max-w-[85%] rounded-lg border px-3 py-2 text-xs ${
                          message.direction === "outbound"
                            ? "ml-auto border-gh-accent/40 bg-gh-accent/10"
                            : "border-gh-border bg-gh-canvas-inset"
                        }`}
                      >
                        <div className="mb-0.5 text-gh-text-secondary">
                          {message.direction === "outbound"
                            ? "我"
                            : message.sender_name || message.sender_id}
                        </div>
                        <div className="whitespace-pre-wrap text-gh-text">{message.text}</div>
                      </div>
                    ))
                  )}
                </div>
                {activeChat && (
                  <div className="mt-3 flex gap-2">
                    <input
                      value={sendText}
                      onChange={(event) => setSendText(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") handleSend();
                      }}
                      placeholder="输入消息，Enter 发送"
                      className="flex-1 rounded-md border border-gh-border bg-gh-canvas-inset px-3 py-1.5 text-sm text-gh-text placeholder-gh-text-secondary focus:border-gh-accent focus:outline-none"
                    />
                    <Button
                      variant="primary"
                      size="sm"
                      loading={busy === "send"}
                      icon={<IconZap size={14} />}
                      onClick={handleSend}
                    >
                      发送
                    </Button>
                  </div>
                )}
              </Card>

              <Card className="p-4">
                <h3 className="mb-2 text-sm font-semibold text-gh-text">群组管理</h3>
                <div className="max-h-80 space-y-1 overflow-y-auto">
                  {groups.length === 0 ? (
                    <EmptyState message="无群组" />
                  ) : (
                    groups.map((group) => (
                      <div
                        key={group.group_id}
                        className="flex items-center justify-between rounded-md border border-gh-border px-2 py-1.5 text-xs"
                      >
                        <div className="min-w-0">
                          <div className="truncate text-gh-text">{group.name}</div>
                          <div className="text-gh-text-secondary">
                            {group.group_id} · {group.member_count} 人
                          </div>
                        </div>
                        <div className="flex gap-1">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleGroupAction(group, "kick")}
                          >
                            踢人
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleGroupAction(group, "ban")}
                          >
                            禁言
                          </Button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </Card>
            </div>
          )}

          {showCreate && (
            <div className="mt-6 rounded-xl border border-gh-border bg-gh-canvas-subtle p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-gh-text">
                <IconPlus size={14} className="text-gh-accent" />
                添加 QQ 实例（NapCat + OneBot 11）
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Input
                  label="实例名称"
                  placeholder="如：主力 QQ"
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                />
                <Input
                  label="OneBot HTTP 地址"
                  placeholder="http://127.0.0.1:3000"
                  value={form.api_base_url}
                  onChange={(event) => setForm({ ...form, api_base_url: event.target.value })}
                />
                <Input
                  label="NapCat WebUI 地址（扫码用）"
                  placeholder="http://127.0.0.1:6099/webui"
                  value={form.webui_url}
                  onChange={(event) => setForm({ ...form, webui_url: event.target.value })}
                />
                <Input
                  label="事件推送 Token"
                  placeholder="自定义随机串，需同步填到 NapCat"
                  value={form.event_token}
                  onChange={(event) => setForm({ ...form, event_token: event.target.value })}
                />
              </div>
              <div className="mt-3 flex justify-end gap-2">
                <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>
                  取消
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  loading={busy === "create"}
                  icon={<IconRefresh size={14} />}
                  onClick={handleCreate}
                >
                  创建
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
