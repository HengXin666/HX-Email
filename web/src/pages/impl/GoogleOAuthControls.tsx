import React, { useState } from "react";
import { api } from "../../api/client";
import { IconKey } from "../../components/icons";
import { GoogleOAuthConfigForm } from "./GoogleOAuthConfigForm";
import { GoogleOAuthLinkFlow } from "./GoogleOAuthLinkFlow";

interface GoogleOAuthControlsProps {
  accountId: number;
  email: string;
  onAuthorized: () => void | Promise<void>;
}

/**
 * Google 一键授权：配置 OAuth 客户端后生成授权链接，用户复制并在任意浏览器
 * 完成授权，系统自动保存并刷新 Gmail Token。链接不会自动打开，避免把当前
 * 浏览器的 Google 会话绑定到授权流程上。
 */
export function GoogleOAuthControls({ accountId, email, onAuthorized }: GoogleOAuthControlsProps) {
  const [configReady, setConfigReady] = useState(false);

  return (
    <div className="rounded-lg border border-gh-accent/30 bg-gh-accent/5 p-3 space-y-3">
      <div className="flex items-start gap-2">
        <IconKey size={15} className="mt-0.5 text-gh-accent" />
        <div className="min-w-0">
          <div className="text-sm font-semibold text-gh-text">Google 一键授权</div>
          <div className="mt-0.5 text-xs leading-relaxed text-gh-text-secondary">
            生成授权链接后自行复制打开，授权完成会自动保存并刷新 Gmail Token。
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

      <GoogleOAuthConfigForm onConfigReady={setConfigReady} />

      <GoogleOAuthLinkFlow
        configReady={configReady}
        prepare={() => api.prepareGoogleOAuth(accountId)}
        onAuthorized={async () => {
          await onAuthorized();
        }}
      />
    </div>
  );
}
