import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import { IconGithub, IconRefresh } from "../../components/icons";
import { Badge, Button, Card, Checkbox, Input } from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import type {
  GithubUserCheckResult,
  GithubUserReport,
  MessagingInstance,
} from "../../types/messaging";
import { GithubOutboundSettings } from "./GithubOutboundSettings";

const USER_KIND: string = "github_user";
const PLACEHOLDER_CLI: string = "/home/you/.local/bin/gh-agent";

const OBSERVE_SWITCHES: readonly { key: string; label: string }[] = [
  { key: "observe_issues", label: "新 issue 与关闭" },
  { key: "observe_pulls", label: "新 PR 与关闭" },
  { key: "observe_comments", label: "全部评论" },
  { key: "observe_ci", label: "CI 运行结果" },
];

const WRAPPER_EXAMPLE: string = [
  "cat > ~/.local/bin/gh-agent <<'SH'",
  "#!/bin/sh",
  'GH_CONFIG_DIR="$HOME/.config/gh-agent" exec gh "$@"',
  "SH",
  "chmod +x ~/.local/bin/gh-agent",
  "~/.local/bin/gh-agent auth login",
].join("\n");

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function isOn(config: Record<string, string>, key: string): boolean {
  return ["1", "true", "on", "yes"].includes((config[key] ?? "").toLowerCase());
}

function ReportLine({ report }: { report: GithubUserReport }) {
  if (report.ok) {
    return (
      <div className="space-y-1 text-xs">
        <div className="flex items-center gap-2">
          <Badge color="#3fb950">已连接</Badge>
          <span className="font-mono text-gh-text">{report.login}</span>
        </div>
        {report.missing_scopes.length > 0 && (
          <p className="text-gh-danger/80">缺少 scope: {report.missing_scopes.join(", ")}</p>
        )}
      </div>
    );
  }
  return (
    <div className="space-y-1 text-xs" role="alert">
      <div className="flex items-center gap-2">
        <Badge color="#f85149">{report.code}</Badge>
        <span className="text-gh-text">{report.message}</span>
      </div>
      {report.hint && <p className="text-gh-text-secondary">{report.hint}</p>}
    </div>
  );
}

/**
 * GitHub 用户账号 (gh CLI) 接入: 只填 CLI 绝对路径与仓库, 点「检查」由服务端运行 CLI 读出登录名;
 * token 只在用户自己的包装脚本里, 网页上没有任何 token 输入. 动作开关复用 App 的组件, 按平台取声明
 * 决策记录: .agents/notes/implemented/feature/2026-11-09-github-cli-account.md
 */
export function GithubUserConnect() {
  const { toast } = useToast();
  const [instance, setInstance] = useState<MessagingInstance | null>(null);
  const [cli, setCli] = useState<string>("");
  const [repository, setRepository] = useState<string>("");
  const [report, setReport] = useState<GithubUserReport | null>(null);
  const [busy, setBusy] = useState<string>("");

  useEffect(() => {
    let alive = true;
    api
      .listInstances()
      .then((items: MessagingInstance[]) => {
        const found = items.find((item: MessagingInstance) => item.kind === USER_KIND);
        if (!alive || !found) return;
        setInstance(found);
        setCli(found.config.cli ?? "");
        setRepository(found.config.repository ?? "");
      })
      .catch((error: unknown) => toast(errorText(error, "加载 GitHub 账号实例失败"), "error"));
    return () => {
      alive = false;
    };
  }, [toast]);

  const check = useCallback(async (): Promise<void> => {
    setBusy("check");
    try {
      const result: GithubUserCheckResult = await api.githubUserSave({
        cli: cli.trim(),
        repository: repository.trim(),
        ...(instance ? { instance_id: instance.id } : {}),
      });
      setInstance(result.instance);
      setReport(result.report);
    } catch (error: unknown) {
      toast(errorText(error, "检查失败"), "error");
    } finally {
      setBusy("");
    }
  }, [cli, instance, repository, toast]);

  const toggleObserve = useCallback(
    async (key: string, enabled: boolean): Promise<void> => {
      if (!instance) return;
      setBusy(key);
      try {
        setInstance(await api.updateConfig(instance.id, { [key]: enabled ? "1" : "0" }));
      } catch (error: unknown) {
        toast(errorText(error, "保存开关失败"), "error");
      } finally {
        setBusy("");
      }
    },
    [instance, toast],
  );

  return (
    <Card className="mt-6 p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-gh-text">
        <IconGithub size={16} className="text-gh-accent" />
        GitHub 账号 (gh CLI)
      </div>
      <p className="mt-2 text-xs leading-relaxed text-gh-text-secondary">
        以真人或专用账号身份收发: 读这个账号的 notifications, 以它的身份回帖. 先在运行本服务的机器上
        为账号建一个 gh 包装脚本并在终端登录, 这里只填脚本路径, 不需要也不接受 token.
      </p>
      <pre className="mt-2 overflow-x-auto rounded-lg border border-gh-border bg-gh-canvas-inset p-2 text-xs text-gh-text">
        {WRAPPER_EXAMPLE}
      </pre>
      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Input
          id="gh-user-cli"
          label="CLI 路径"
          placeholder={PLACEHOLDER_CLI}
          value={cli}
          onChange={(event) => setCli(event.target.value)}
        />
        <Input
          id="gh-user-repo"
          label="仓库 (owner/name)"
          placeholder="owner/name"
          value={repository}
          onChange={(event) => setRepository(event.target.value)}
        />
      </div>
      <div className="mt-3">
        <Button
          size="sm"
          loading={busy === "check"}
          disabled={!cli.trim() || !repository.trim()}
          icon={<IconRefresh size={14} />}
          onClick={() => void check()}
        >
          检查
        </Button>
      </div>
      {report && (
        <div className="mt-3">
          <ReportLine report={report} />
        </div>
      )}
      {instance && (
        <div className="mt-4 space-y-4">
          <div>
            <div className="mb-1.5 text-xs font-medium text-gh-text-muted">入站范围</div>
            <p className="mb-2 text-xs text-gh-text-secondary">
              全关时只收 notifications 里与本账号有关的 (被 @, 被请求 review, 被指派...).
            </p>
            <div className="space-y-2">
              {OBSERVE_SWITCHES.map((item) => (
                <Checkbox
                  key={item.key}
                  label={<span className="text-xs text-gh-text">{item.label}</span>}
                  checked={isOn(instance.config, item.key)}
                  disabled={busy !== ""}
                  onChange={(checked: boolean) => void toggleObserve(item.key, checked)}
                />
              ))}
            </div>
          </div>
          <GithubOutboundSettings instance={instance} platform={USER_KIND} />
        </div>
      )}
    </Card>
  );
}
