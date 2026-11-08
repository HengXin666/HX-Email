import React, { useState } from "react";
import { api } from "../../api/client";
import { IconPlus } from "../../components/icons";
import { Badge, Button, Card, Checkbox, Input, Select } from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import type {
  RouterDelivery,
  RouterDirection,
  RouterSource,
  RouterSubscription,
} from "../../types/messaging";
import { sourceChoices } from "./subscription_snippets";

interface Props {
  sources: RouterSource[];
  onCreated: (created: RouterSubscription) => void;
}

const message = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback;

/** New subscription: source, filter, and how it is delivered (pull or webhook). */
export const SubscriptionCreateForm: React.FC<Props> = ({ sources, onCreated }) => {
  const { toast } = useToast();
  const [form, setForm] = useState({
    source: "",
    name: "",
    contains: "",
    direction: "inbound" as RouterDirection,
    mentionSelf: false,
    excludeSelf: true,
    earliest: false,
    delivery: "pull" as RouterDelivery,
    webhookUrl: "",
  });

  const create = async () => {
    if (!form.source.trim()) {
      toast("先填来源，例如 qq:1/group", "error");
      return;
    }
    if (form.delivery === "webhook" && !/^https?:\/\//.test(form.webhookUrl.trim())) {
      toast("Webhook 需要一个 http(s) 地址", "error");
      return;
    }
    try {
      const created = await api.createSubscription({
        source: form.source.trim(),
        name: form.name.trim(),
        from: form.earliest ? "earliest" : "now",
        delivery: form.delivery,
        ...(form.delivery === "webhook" ? { webhook_url: form.webhookUrl.trim() } : {}),
        filter: {
          direction: form.direction,
          contains: form.contains.trim(),
          mention_self: form.mentionSelf,
          exclude_self: form.excludeSelf,
        },
      });
      toast(`已创建订阅 #${created.id}`, "success");
      onCreated(created);
    } catch (error) {
      toast(message(error, "创建失败"), "error");
    }
  };

  return (
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
          label="投递方式"
          value={form.delivery}
          onChange={(value) => setForm({ ...form, delivery: value as RouterDelivery })}
          options={[
            { value: "pull", label: "拉取 (长轮询 / SSE / WS)" },
            { value: "webhook", label: "Webhook 推送" },
          ]}
          className="w-56"
        />
        {form.delivery === "webhook" && (
          <div className="flex-1 min-w-64">
            <Input
              label="Webhook 地址"
              placeholder="https://your-agent.example/hx-hook"
              value={form.webhookUrl}
              onChange={(event) => setForm({ ...form, webhookUrl: event.target.value })}
            />
          </div>
        )}
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
  );
};
