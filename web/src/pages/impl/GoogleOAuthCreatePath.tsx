import React, { useState } from "react";
import { api } from "../../api/client";
import { IconKey } from "../../components/icons";
import { GoogleOAuthConfigForm } from "./GoogleOAuthConfigForm";
import { GoogleOAuthLinkFlow } from "./GoogleOAuthLinkFlow";

interface GoogleOAuthCreatePathProps {
  groupId?: number | null;
  onChanged: () => void | Promise<void>;
}

/**
 * Google 一键授权（新增账号）：无需手动输入 Gmail 地址。生成授权链接后，
 * 用户在任意浏览器完成 Google 授权，回调会从 Google 读取真实邮箱并自动
 * 创建（或更新）对应的 Gmail 账号、保存凭证。
 */
export function GoogleOAuthCreatePath({ groupId = null, onChanged }: GoogleOAuthCreatePathProps) {
  const [configReady, setConfigReady] = useState(false);

  return (
    <div className="rounded-lg border border-gh-accent/30 bg-gh-accent/5 p-4 space-y-3">
      <div className="flex items-start gap-2">
        <IconKey size={15} className="mt-0.5 text-gh-accent" />
        <div>
          <div className="text-sm font-semibold text-gh-text">Google 一键授权</div>
          <p className="mt-1 text-xs leading-relaxed text-gh-text-secondary">
            无需填写邮箱：生成授权链接后，在需要授权的浏览器中打开并登录对应的 Google
            账号，系统会自动识别邮箱、创建 Gmail 账号并保存 Token。无需 Gmail 登录密码。
          </p>
        </div>
      </div>

      <GoogleOAuthConfigForm onConfigReady={setConfigReady} />

      <GoogleOAuthLinkFlow
        configReady={configReady}
        prepare={() => api.prepareGoogleOAuthNew(groupId)}
        onAuthorized={async () => {
          await onChanged();
        }}
        actionLabel="生成授权链接"
      />
    </div>
  );
}
