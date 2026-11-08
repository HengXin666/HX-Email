import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import { IconCheck, IconCopy, IconKey, IconTrash } from "../../components/icons";
import { Button, Card, Input } from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import type { RouterApiKey, RouterSubscription } from "../../types/messaging";
import { copyToClipboard } from "../../utils/clipboard";
import { buildSnippets } from "./subscription_snippets";

interface Props {
  selected: RouterSubscription | null;
}

const CopyIcon: React.FC<{ text: string }> = ({ text }) => {
  const { toast } = useToast();
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      aria-label="复制"
      className="text-gh-text-muted hover:text-gh-text p-1"
      onClick={async () => {
        if (!(await copyToClipboard(text))) {
          toast("复制失败，请手动复制", "error");
          return;
        }
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
    >
      {done ? <IconCheck size={12} className="text-gh-success" /> : <IconCopy size={12} />}
    </button>
  );
};

/** Router API keys plus copy-paste snippets bound to the selected subscription. */
export const SubscriptionIntegration: React.FC<Props> = ({ selected }) => {
  const { toast } = useToast();
  const [keys, setKeys] = useState<RouterApiKey[]>([]);
  const [keyName, setKeyName] = useState("agent");
  const [issued, setIssued] = useState("");
  const [tab, setTab] = useState("curl");

  const loadKeys = useCallback(async () => {
    try {
      const data = await api.listRouterKeys();
      setKeys(data.keys.filter((key) => !key.revoked_at));
    } catch (error) {
      toast(error instanceof Error ? error.message : "读取密钥失败", "error");
    }
  }, [toast]);

  useEffect(() => {
    void loadKeys();
  }, [loadKeys]);

  const createKey = async () => {
    try {
      const created = await api.createRouterKey(keyName.trim() || "agent");
      setIssued(created.key);
      toast("已创建，密钥只显示这一次", "success");
      await loadKeys();
    } catch (error) {
      toast(error instanceof Error ? error.message : "创建失败", "error");
    }
  };

  const revokeKey = async (id: number) => {
    try {
      await api.revokeRouterKey(id);
      await loadKeys();
    } catch (error) {
      toast(error instanceof Error ? error.message : "吊销失败", "error");
    }
  };

  const snippets = useMemo(
    () =>
      buildSnippets({
        baseUrl: `${window.location.origin}/api/v1`,
        token: issued || "<hxr_router_key>",
        subscriptionId: selected?.id ?? null,
        source: selected?.source ?? "",
      }),
    [issued, selected],
  );
  const current = snippets.find((item) => item.key === tab) ?? snippets[0];

  return (
    <Card className="p-4 space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-gh-text">快速对接</h3>
        <p className="text-xs text-gh-text-secondary mt-1">
          给 Agent 发一把 hxr_ 路由密钥（只能读写消息，不能管理密钥或解除熔断），
          再把下面的代码贴过去。{selected ? `已代入订阅 #${selected.id}。` : "先在左边选一个订阅。"}
        </p>
      </div>

      <div className="flex items-end gap-2">
        <Input
          label="密钥名称"
          value={keyName}
          onChange={(event) => setKeyName(event.target.value)}
          className="w-40"
        />
        <Button variant="primary" size="sm" icon={<IconKey size={12} />} onClick={createKey}>
          新建路由密钥
        </Button>
      </div>
      {issued && (
        <div className="flex items-center gap-2 rounded-md border border-gh-success/40 bg-gh-success/10 px-3 py-2">
          <code
            className="text-xs font-mono text-gh-text break-all flex-1"
            data-testid="issued-key"
          >
            {issued}
          </code>
          <CopyIcon text={issued} />
        </div>
      )}
      {keys.length > 0 && (
        <ul className="space-y-1">
          {keys.map((key) => (
            <li key={key.id} className="flex items-center gap-2 text-xs text-gh-text-secondary">
              <code className="font-mono text-gh-text">{key.key_prefix}…</code>
              <span>{key.name}</span>
              <span className="flex-1">
                {key.last_used_at ? `最近使用 ${key.last_used_at}` : "未使用"}
              </span>
              <button
                type="button"
                aria-label={`吊销 ${key.name}`}
                className="text-gh-text-muted hover:text-gh-danger p-1"
                onClick={() => revokeKey(key.id)}
              >
                <IconTrash size={12} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-1 border-b border-gh-border">
        {snippets.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setTab(item.key)}
            className={`px-3 py-1.5 text-xs border-b-2 ${
              item.key === current.key
                ? "border-gh-accent text-gh-accent"
                : "border-transparent text-gh-text-muted hover:text-gh-text"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="relative rounded-lg border border-gh-border bg-gh-canvas-inset">
        <div className="absolute right-2 top-2">
          <CopyIcon text={current.code} />
        </div>
        <pre className="p-3 pr-8 text-xs font-mono text-gh-text overflow-x-auto leading-relaxed">
          <code>{current.code}</code>
        </pre>
      </div>
    </Card>
  );
};
