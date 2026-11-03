import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { IconCheck, IconGithub, IconLink, IconRefresh } from "../../components/icons";
import { Badge, Button, Card } from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import type {
  GithubInstallation,
  GithubManifestStart,
  GithubVerifyResult,
  MessagingInstance,
} from "../../types/messaging";

const GITHUB_KIND: string = "github";
const CALLBACK_KEYS: readonly string[] = ["connected", "slug", "error"];

const ERROR_MESSAGES: Record<string, string> = {
  invalid_state: "授权链接已过期或已被使用, 请重新点一次「用 GitHub 一键创建」",
  conversion_failed: "GitHub 没有返回 App 凭据, 请重新创建",
  conversion_incomplete: "GitHub 返回的 App 凭据不完整, 请重新创建",
  encryption_unavailable: "服务端未配置加密密钥, 无法安全保存 App 私钥, 请先联系管理员配置",
  save_failed: "App 已在 GitHub 创建, 但保存到本服务失败, 请重试",
  missing_code_or_state: "GitHub 回跳缺少必要参数, 请重新创建",
};

type BusyKey = "" | "start" | "verify" | `attach-${number}`;

interface CallbackParams {
  connected: boolean;
  slug: string;
  error: string;
}

export function describeGithubError(reason: string): string {
  return ERROR_MESSAGES[reason] ?? `GitHub App 接入失败 (${reason})`;
}

/** Full-page form POST: GitHub must show its own confirmation page, so fetch cannot do this. */
function submitManifest(start: GithubManifestStart): void {
  const form: HTMLFormElement = document.createElement("form");
  form.method = "post";
  form.action = start.action;
  form.style.display = "none";
  const add = (name: string, value: string): void => {
    const input: HTMLInputElement = document.createElement("input");
    input.type = "hidden";
    input.name = name;
    input.value = value;
    form.appendChild(input);
  };
  add("manifest", JSON.stringify(start.manifest));
  add("state", start.state);
  document.body.appendChild(form);
  form.submit();
}

function readCallbackParams(): CallbackParams {
  const params: URLSearchParams = new URLSearchParams(window.location.search);
  return {
    connected: params.get("connected") === "1",
    slug: params.get("slug") ?? "",
    error: params.get("error") ?? "",
  };
}

function clearCallbackParams(): void {
  const url: URL = new URL(window.location.href);
  for (const key of CALLBACK_KEYS) url.searchParams.delete(key);
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

const FlagRow: React.FC<{ label: string; ok: boolean }> = ({ label, ok }) => (
  <div className="flex items-center justify-between text-xs">
    <span className="text-gh-text-secondary">{label}</span>
    <Badge color={ok ? "#3fb950" : "#f85149"}>{ok ? "已配置" : "未配置"}</Badge>
  </div>
);

/**
 * GitHub App 一键接入: 管理员点按钮后整页 POST manifest 到 GitHub, 在 GitHub 上确认创建,
 * 回跳 /messaging 后验证 App 并把某个 installation 绑定到本服务的 GitHub 实例.
 * manifest 必须整页表单提交, 不能 fetch: 用户要在 GitHub 页面上确认创建.
 *
 * 决策记录: .agents/notes/implemented/feature/2026-11-03-github-app-manifest-flow.md
 */
export function GithubAppConnect() {
  const { toast } = useToast();
  const [instanceId, setInstanceId] = useState<number | null>(null);
  const [result, setResult] = useState<GithubVerifyResult | null>(null);
  const [attachedId, setAttachedId] = useState<number | null>(null);
  const [busy, setBusy] = useState<BusyKey>("");
  const [loading, setLoading] = useState<boolean>(true);
  const callbackHandledRef = useRef<boolean>(false);

  const verify = useCallback(
    async (id: number, silent: boolean): Promise<void> => {
      setBusy("verify");
      try {
        const verified: GithubVerifyResult = await api.githubVerify(id);
        setResult(verified);
        if (!silent) {
          toast(
            verified.verified
              ? "连接正常, 已从 GitHub 读取安装列表"
              : "GitHub 未通过验证, 请检查 App 是否仍存在",
            verified.verified ? "success" : "error",
          );
        }
      } catch (error: unknown) {
        if (!silent) toast(errorText(error, "验证连接失败"), "error");
      } finally {
        setBusy("");
      }
    },
    [toast],
  );

  useEffect(() => {
    if (!callbackHandledRef.current) {
      callbackHandledRef.current = true;
      const params: CallbackParams = readCallbackParams();
      if (params.connected) toast(`GitHub App ${params.slug} 已创建并保存`, "success");
      else if (params.error) toast(describeGithubError(params.error), "error");
      if (params.connected || params.error) clearCallbackParams();
    }
    const load = async (): Promise<void> => {
      try {
        const instances: MessagingInstance[] = await api.listInstances();
        const github: MessagingInstance | undefined = instances.find(
          (instance: MessagingInstance) => instance.kind === GITHUB_KIND,
        );
        if (github) {
          setInstanceId(github.id);
          await verify(github.id, true);
        }
      } catch (error: unknown) {
        toast(errorText(error, "加载 GitHub 实例失败"), "error");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [toast, verify]);

  const handleStart = async (): Promise<void> => {
    setBusy("start");
    try {
      const start: GithubManifestStart = await api.githubManifestStart(window.location.origin);
      setInstanceId(start.instance_id);
      toast("正在跳转到 GitHub, 请在 GitHub 页面确认创建", "info");
      submitManifest(start);
    } catch (error: unknown) {
      toast(errorText(error, "生成 GitHub App 清单失败"), "error");
      setBusy("");
    }
  };

  const handleAttach = async (installation: GithubInstallation): Promise<void> => {
    if (instanceId === null) return;
    setBusy(`attach-${installation.id}`);
    try {
      const attached = await api.githubAttach(installation.id, instanceId);
      setAttachedId(attached.installation.id);
      toast(`已绑定 ${attached.installation.account || installation.id}`, "success");
    } catch (error: unknown) {
      toast(errorText(error, "绑定安装失败"), "error");
    } finally {
      setBusy("");
    }
  };

  const config = result?.app_config;
  const installations: GithubInstallation[] = result?.installations ?? [];

  return (
    <Card className="mt-6 p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-gh-text">
          <IconGithub size={16} className="text-gh-accent" />
          GitHub App 接入
        </div>
        {config && (
          <Badge color={result?.verified ? "#3fb950" : "#d29922"}>
            {result?.verified ? "已接入" : "待验证"}
          </Badge>
        )}
      </div>

      {loading ? (
        <p className="mt-2 text-xs text-gh-text-secondary">正在读取 GitHub 接入状态...</p>
      ) : !config ? (
        <div className="mt-2 space-y-3">
          <p className="text-xs leading-relaxed text-gh-text-secondary">
            点下面的按钮会跳到 GitHub, 确认后自动创建 App 并把私钥与 webhook secret
            加密保存到本服务.
          </p>
          <Button
            variant="primary"
            size="sm"
            loading={busy === "start"}
            icon={<IconGithub size={14} />}
            onClick={() => void handleStart()}
          >
            用 GitHub 一键创建
          </Button>
        </div>
      ) : (
        <div className="mt-3 space-y-3">
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-gh-text-secondary">App</span>
              <span className="font-mono text-gh-text">{config.app_slug}</span>
            </div>
            <FlagRow label="私钥" ok={config.has_private_key} />
            <FlagRow label="Webhook secret" ok={config.has_webhook_secret} />
          </div>

          <Button
            size="sm"
            loading={busy === "verify"}
            icon={<IconRefresh size={14} />}
            onClick={() => instanceId !== null && void verify(instanceId, false)}
          >
            验证连接
          </Button>

          <div>
            <div className="mb-1.5 text-xs font-medium text-gh-text-muted">安装列表</div>
            {installations.length === 0 ? (
              <p className="text-xs text-gh-text-secondary">
                还没有安装.
                <a
                  href={`https://github.com/apps/${config.app_slug}/installations/new`}
                  target="_blank"
                  rel="noreferrer"
                  className="ml-1 text-gh-accent hover:underline"
                >
                  去 GitHub 安装这个 App
                </a>
                , 装好后点「验证连接」.
              </p>
            ) : (
              <div className="space-y-2">
                {installations.map((installation: GithubInstallation) => (
                  <div
                    key={installation.id}
                    className="flex items-center justify-between gap-2 rounded-lg border border-gh-border bg-gh-canvas-inset px-3 py-2"
                  >
                    <div className="min-w-0 text-xs">
                      <div className="truncate font-medium text-gh-text">
                        {installation.account || "未知账号"}
                      </div>
                      <div className="text-gh-text-muted">#{installation.id}</div>
                    </div>
                    {attachedId === installation.id ? (
                      <Badge color="#3fb950">
                        <IconCheck size={12} /> 已绑定
                      </Badge>
                    ) : (
                      <Button
                        size="sm"
                        variant="subtle"
                        loading={busy === `attach-${installation.id}`}
                        icon={<IconLink size={14} />}
                        onClick={() => void handleAttach(installation)}
                      >
                        绑定到这个实例
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
