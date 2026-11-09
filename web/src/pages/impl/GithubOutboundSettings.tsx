import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { Checkbox } from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import type { MessagingInstance, RouterActionSpec } from "../../types/messaging";

const DISABLED_ACTIONS_KEY: string = "disabled_actions";
// message_send 也是控制台发送的入口, 不在这里关
const ALWAYS_ON: ReadonlySet<string> = new Set<string>(["message_send"]);

export function parseDisabled(raw: string | undefined): Set<string> {
  return new Set<string>(
    (raw ?? "")
      .split(",")
      .map((name: string) => name.trim())
      .filter((name: string) => name.length > 0),
  );
}

export function serializeDisabled(disabled: ReadonlySet<string>): string {
  return [...disabled].sort().join(",");
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

interface Props {
  instance: MessagingInstance;
  /** 能力声明里的平台名; App 卡片不传, 即 github */
  platform?: string;
}

/**
 * 按实例开关 GitHub 出站动作: 动作列表取自能力声明, 关掉的写进实例配置 disabled_actions,
 * 默认空即全部开启; 后端 invoke_action 拒绝被关掉的动作 (422 action_not_supported)
 * 决策记录: .agents/notes/implemented/feature/2026-11-09-github-outbound-actions.md
 */
export function GithubOutboundSettings({ instance, platform = "github" }: Props) {
  const { toast } = useToast();
  const [actions, setActions] = useState<RouterActionSpec[]>([]);
  const [disabled, setDisabled] = useState<Set<string>>(() =>
    parseDisabled(instance.config[DISABLED_ACTIONS_KEY]),
  );
  const [saving, setSaving] = useState<string>("");

  useEffect(() => {
    let alive = true;
    api
      .githubActions(platform)
      .then((found: RouterActionSpec[]) => {
        if (alive) setActions(found.filter((spec: RouterActionSpec) => !ALWAYS_ON.has(spec.name)));
      })
      .catch((error: unknown) => toast(errorText(error, "读取 GitHub 动作列表失败"), "error"));
    return () => {
      alive = false;
    };
  }, [platform, toast]);

  const toggle = useCallback(
    async (name: string, enabled: boolean): Promise<void> => {
      const next: Set<string> = new Set<string>(disabled);
      if (enabled) next.delete(name);
      else next.add(name);
      setSaving(name);
      try {
        const saved: MessagingInstance = await api.updateConfig(instance.id, {
          [DISABLED_ACTIONS_KEY]: serializeDisabled(next),
        });
        setDisabled(parseDisabled(saved.config[DISABLED_ACTIONS_KEY]));
        toast(`${name} 已${enabled ? "开启" : "关闭"}`, "success");
      } catch (error: unknown) {
        toast(errorText(error, "保存动作开关失败"), "error");
      } finally {
        setSaving("");
      }
    },
    [disabled, instance.id, toast],
  );

  if (actions.length === 0) return null;

  return (
    <div>
      <div className="mb-1.5 text-xs font-medium text-gh-text-muted">出站动作</div>
      <p className="mb-2 text-xs text-gh-text-secondary">
        关掉的动作经 action_invoke 调用时直接被拒绝; 发消息 (message_send) 不受影响.
      </p>
      <div className="space-y-2">
        {actions.map((spec: RouterActionSpec) => (
          <div key={spec.name} className="flex items-start justify-between gap-2">
            <Checkbox
              label={<span className="font-mono text-xs text-gh-text">{spec.name}</span>}
              checked={!disabled.has(spec.name)}
              disabled={saving !== ""}
              onChange={(checked: boolean) => void toggle(spec.name, checked)}
            />
            <span className="text-right text-xs text-gh-text-muted">
              {spec.requires.join(", ")}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
