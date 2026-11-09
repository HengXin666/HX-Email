import React, { useState } from "react";
import { Button } from "../../components/ui/Primitives";

/** Scopes a router key can hold; order and wording follow docs/messaging-router.md 8.3. */
const ROUTER_SCOPES: { value: string; label: string }[] = [
  { value: "router:read", label: "读取（来源、会话、消息、投递状态、资源）" },
  { value: "router:send", label: "发送消息" },
  { value: "router:actions", label: "执行平台动作" },
  { value: "subscriptions", label: "持久订阅" },
  { value: "resources:subscribe", label: "MCP 资源订阅通知" },
  { value: "mcp", label: "连接 /mcp" },
  { value: "admin", label: "全部（含以后新增的权限）" },
];

/** New keys default to what keys could do before scopes existed: everything but admin. */
export const DEFAULT_SCOPES: string[] = ROUTER_SCOPES.map((item) => item.value).filter(
  (value) => value !== "admin",
);

interface PickerProps {
  value: string[];
  onChange: (next: string[]) => void;
  idPrefix: string;
}

/** Checkbox list of scopes; keeps the canonical order whatever was clicked first. */
export function ScopePicker({ value, onChange, idPrefix }: PickerProps): React.ReactElement {
  const toggle = (scope: string) => {
    const wanted = value.includes(scope) ? value.filter((v) => v !== scope) : [...value, scope];
    onChange(ROUTER_SCOPES.map((item) => item.value).filter((v) => wanted.includes(v)));
  };
  return (
    <fieldset className="flex flex-wrap gap-x-4 gap-y-1">
      <legend className="sr-only">密钥权限</legend>
      {ROUTER_SCOPES.map((item) => (
        <label
          key={item.value}
          htmlFor={`${idPrefix}-${item.value}`}
          className="flex items-center gap-1 text-xs text-gh-text-secondary"
        >
          <input
            id={`${idPrefix}-${item.value}`}
            type="checkbox"
            checked={value.includes(item.value)}
            onChange={() => toggle(item.value)}
          />
          <code className="font-mono">{item.value}</code>
          <span>{item.label}</span>
        </label>
      ))}
    </fieldset>
  );
}

interface EditorProps {
  keyId: number;
  scopes: string[];
  onSave: (keyId: number, scopes: string[]) => Promise<void>;
}

/** Shows a key's scopes; "改权限" opens the picker, save needs at least one scope. */
export function KeyScopeEditor({ keyId, scopes, onSave }: EditorProps): React.ReactElement {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string[]>(scopes);
  if (!editing) {
    return (
      <span className="flex items-center gap-2">
        <span data-testid={`scopes-${keyId}`}>{scopes.join(" ") || "无权限"}</span>
        <button
          type="button"
          className="text-gh-accent hover:underline"
          onClick={() => {
            setDraft(scopes);
            setEditing(true);
          }}
        >
          改权限
        </button>
      </span>
    );
  }
  return (
    <span className="flex flex-col gap-1">
      <ScopePicker value={draft} onChange={setDraft} idPrefix={`key-${keyId}`} />
      <span className="flex gap-2">
        <Button
          size="sm"
          variant="primary"
          disabled={draft.length === 0}
          onClick={async () => {
            await onSave(keyId, draft);
            setEditing(false);
          }}
        >
          保存权限
        </Button>
        <Button size="sm" onClick={() => setEditing(false)}>
          取消
        </Button>
      </span>
    </span>
  );
}
