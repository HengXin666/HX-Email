import React, { useEffect, useState } from "react";
import { api } from "../../api/client";
import { IconCheck, IconKey, IconSettings } from "../../components/icons";
import { Button, Input } from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import type { GoogleOAuthConfig } from "../../types";
import { GoogleOAuthGuide } from "./GoogleOAuthGuide";

interface GoogleOAuthControlsProps {
  accountId: number;
  email: string;
  onAuthorized: () => void | Promise<void>;
}

interface GoogleOAuthMessage {
  type: "hx-google-oauth";
  success: boolean;
  message: string;
}

const defaultRedirectUri = (): string => `${window.location.origin}/api/v1/google-oauth/callback`;

function isGoogleOAuthMessage(value: unknown): value is GoogleOAuthMessage {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return (
    candidate.type === "hx-google-oauth" &&
    typeof candidate.success === "boolean" &&
    typeof candidate.message === "string"
  );
}

export function GoogleOAuthControls({ accountId, email, onAuthorized }: GoogleOAuthControlsProps) {
  const { toast } = useToast();
  const [config, setConfig] = useState<GoogleOAuthConfig>({
    client_id: "",
    redirect_uri: defaultRedirectUri(),
    has_client_secret: false,
  });
  const [clientSecret, setClientSecret] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [hasSavedConfig, setHasSavedConfig] = useState(false);
  const [action, setAction] = useState<"save" | "authorize" | null>(null);

  useEffect(() => {
    let isCancelled = false;
    api
      .getGoogleOAuthConfig()
      .then((remote: GoogleOAuthConfig) => {
        if (isCancelled) return;
        setConfig({
          ...remote,
          redirect_uri: remote.redirect_uri || defaultRedirectUri(),
        });
        setHasSavedConfig(Boolean(remote.client_id && remote.redirect_uri));
      })
      .catch((error: unknown) => {
        if (!isCancelled)
          toast(error instanceof Error ? error.message : "加载 OAuth 配置失败", "error");
      })
      .finally(() => {
        if (!isCancelled) setIsLoading(false);
      });
    return () => {
      isCancelled = true;
    };
  }, [toast]);

  useEffect(() => {
    const handleMessage = (event: MessageEvent<unknown>): void => {
      if (!isGoogleOAuthMessage(event.data)) return;
      if (!event.data.success) {
        toast(event.data.message, "error");
        return;
      }
      toast(`${email} Google 授权成功`, "success");
      void onAuthorized();
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [email, onAuthorized, toast]);

  const handleSave = async (): Promise<void> => {
    setAction("save");
    try {
      const saved = await api.saveGoogleOAuthConfig({
        client_id: config.client_id.trim(),
        client_secret: clientSecret.trim(),
        redirect_uri: config.redirect_uri.trim(),
      });
      setConfig(saved);
      setClientSecret("");
      setHasSavedConfig(Boolean(saved.client_id && saved.redirect_uri));
      toast("Google OAuth 配置已保存", "success");
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "保存 OAuth 配置失败", "error");
    } finally {
      setAction(null);
    }
  };

  const handleAuthorize = async (): Promise<void> => {
    setAction("authorize");
    try {
      const prepared = await api.prepareGoogleOAuth(accountId);
      const popup = window.open(
        prepared.authorization_url,
        "hx-google-oauth",
        "popup=yes,width=560,height=720,resizable=yes,scrollbars=yes",
      );
      if (!popup) toast("浏览器阻止了授权弹窗，请允许此站点打开弹窗", "error");
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "生成 Google 授权链接失败", "error");
    } finally {
      setAction(null);
    }
  };

  return (
    <div className="rounded-lg border border-gh-accent/30 bg-gh-accent/5 p-3 space-y-3">
      <div className="flex items-start gap-2">
        <IconKey size={15} className="mt-0.5 text-gh-accent" />
        <div className="min-w-0">
          <div className="text-sm font-semibold text-gh-text">Google 一键授权</div>
          <div className="mt-0.5 text-xs leading-relaxed text-gh-text-secondary">
            首次填写 Google Cloud OAuth 客户端；之后点击授权即可自动保存并刷新 Gmail Token。
            <a
              href="https://console.cloud.google.com/apis/credentials"
              target="_blank"
              rel="noreferrer"
              className="ml-1 text-gh-accent hover:underline"
            >
              打开 Google Cloud 凭据
            </a>
          </div>
        </div>
      </div>

      {!isLoading && (
        <div className="space-y-2">
          <GoogleOAuthGuide redirectUri={config.redirect_uri} hasSavedConfig={hasSavedConfig} />
          <Input
            label="Google OAuth Client ID"
            value={config.client_id}
            onChange={(event) => {
              setHasSavedConfig(false);
              setConfig((current) => ({ ...current, client_id: event.target.value }));
            }}
            placeholder="xxxxxxxx.apps.googleusercontent.com"
          />
          <Input
            label={
              config.has_client_secret ? "Client Secret（已保存，留空保持不变）" : "Client Secret"
            }
            type="password"
            value={clientSecret}
            onChange={(event) => {
              setHasSavedConfig(false);
              setClientSecret(event.target.value);
            }}
            placeholder={config.has_client_secret ? "已安全保存" : "Google OAuth Client Secret"}
          />
          <Input
            label="授权回调地址"
            value={config.redirect_uri}
            onChange={(event) => {
              setHasSavedConfig(false);
              setConfig((current) => ({ ...current, redirect_uri: event.target.value }));
            }}
          />
          <div className="flex items-center justify-between gap-2 pt-1">
            <span className="inline-flex items-center gap-1 text-[11px] text-gh-text-secondary">
              {hasSavedConfig ? (
                <IconCheck size={11} className="text-gh-success" />
              ) : (
                <IconSettings size={11} />
              )}
              {hasSavedConfig ? "OAuth 客户端已配置" : "请先保存 OAuth 客户端配置"}
            </span>
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={handleSave} loading={action === "save"}>
                保存配置
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleAuthorize}
                loading={action === "authorize"}
                disabled={!hasSavedConfig}
              >
                使用 Google 授权
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
