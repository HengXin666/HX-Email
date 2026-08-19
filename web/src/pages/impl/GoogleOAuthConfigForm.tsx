import React, { useEffect, useState } from "react";
import { api } from "../../api/client";
import { IconCheck, IconSettings } from "../../components/icons";
import { Button, Input } from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import type { GoogleOAuthConfig } from "../../types";
import { GoogleOAuthGuide } from "./GoogleOAuthGuide";

const defaultRedirectUri = (): string => `${window.location.origin}/api/v1/google-oauth/callback`;

interface GoogleOAuthConfigFormProps {
  onConfigReady?: (ready: boolean) => void;
}

/**
 * Google Cloud OAuth client configuration (Client ID / Secret / Redirect URI).
 * The saved config lives server-side in system_settings; the authorize link
 * is generated against it.
 */
export function GoogleOAuthConfigForm({ onConfigReady }: GoogleOAuthConfigFormProps) {
  const { toast } = useToast();
  const [config, setConfig] = useState<GoogleOAuthConfig>({
    client_id: "",
    redirect_uri: defaultRedirectUri(),
    has_client_secret: false,
  });
  const [clientSecret, setClientSecret] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [hasSavedConfig, setHasSavedConfig] = useState(false);
  const [action, setAction] = useState<"save" | null>(null);

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
        const ready = Boolean(remote.client_id && remote.redirect_uri);
        setHasSavedConfig(ready);
        onConfigReady?.(ready);
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

  const notifyReady = (ready: boolean): void => {
    setHasSavedConfig(ready);
    onConfigReady?.(ready);
  };

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
      notifyReady(Boolean(saved.client_id && saved.redirect_uri));
      toast("Google OAuth 配置已保存", "success");
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "保存 OAuth 配置失败", "error");
    } finally {
      setAction(null);
    }
  };

  if (isLoading) return null;

  return (
    <div className="space-y-2">
      <GoogleOAuthGuide redirectUri={config.redirect_uri} hasSavedConfig={hasSavedConfig} />
      <Input
        label="Google OAuth Client ID"
        value={config.client_id}
        onChange={(event) => {
          notifyReady(false);
          setConfig((current) => ({ ...current, client_id: event.target.value }));
        }}
        placeholder="xxxxxxxx.apps.googleusercontent.com"
      />
      <Input
        label={config.has_client_secret ? "Client Secret（已保存，留空保持不变）" : "Client Secret"}
        type="password"
        value={clientSecret}
        onChange={(event) => {
          notifyReady(false);
          setClientSecret(event.target.value);
        }}
        placeholder={config.has_client_secret ? "已安全保存" : "Google OAuth Client Secret"}
      />
      <Input
        label="授权回调地址"
        value={config.redirect_uri}
        onChange={(event) => {
          notifyReady(false);
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
        <Button variant="ghost" size="sm" onClick={handleSave} loading={action === "save"}>
          保存配置
        </Button>
      </div>
    </div>
  );
}
