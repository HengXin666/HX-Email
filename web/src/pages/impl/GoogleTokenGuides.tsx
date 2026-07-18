import React from "react";
import { IconCheck, IconCode, IconKey } from "../../components/icons";
import { Card } from "../../components/ui/Primitives";

const Step: React.FC<{ number: number; title: string; children: React.ReactNode }> = ({
  number,
  title,
  children,
}) => (
  <div className="flex gap-3 rounded-lg border border-gh-border bg-gh-canvas-inset p-3">
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-gh-accent/20 bg-gh-accent/10 text-xs font-semibold text-gh-accent">
      {number}
    </div>
    <div>
      <div className="text-sm font-semibold text-gh-text">{title}</div>
      <div className="mt-1 text-sm leading-relaxed text-gh-text-secondary">{children}</div>
    </div>
  </div>
);

const CodeBlock: React.FC<{ children: string }> = ({ children }) => (
  <pre className="overflow-x-auto rounded-lg border border-gh-border bg-gh-canvas-inset px-4 py-3 text-xs leading-relaxed text-gh-text font-mono">
    <code>{children}</code>
  </pre>
);

export function GoogleTokenGuide() {
  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_320px]">
      <Card className="p-5">
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-gh-text">
          <IconKey size={14} /> Google 一键授权流程
        </h2>
        <div className="space-y-3">
          <Step number={1} title="创建或选择 Gmail 账号">
            Token 页面可以选择已有 Gmail，也可以先创建账号记录再继续授权。
          </Step>
          <Step number={2} title="配置 Google Cloud OAuth 客户端">
            按页面向导创建 Web application，保存 Client ID、Secret 和完全一致的回调地址。
          </Step>
          <Step number={3} title="使用 Google 授权">
            在弹窗中选择与 Gmail 地址一致的 Google 账号并同意邮件权限。
          </Step>
          <Step number={4} title="自动持久化">
            回调会校验账号身份，并把 Refresh Token 加密写入账号，无需复制粘贴。
          </Step>
        </div>
      </Card>
      <Card className="p-5">
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-gh-text">
          <IconCheck size={14} /> 持久化与安全
        </h2>
        <div className="space-y-3 text-sm leading-relaxed text-gh-text-secondary">
          <p>Google Client Secret 和 Refresh Token 均加密保存，页面不会回显。</p>
          <p>授权 Google 账号必须与本地 Gmail 地址一致，避免 Token 绑错账号。</p>
          <p>External + Testing 模式的邮件 Refresh Token 通常会在 7 天后失效。</p>
        </div>
      </Card>
    </div>
  );
}

export function GoogleTokenApiGuide() {
  return (
    <div className="space-y-5">
      <Card className="p-5">
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-gh-text">
          <IconCode size={14} /> Google OAuth API 顺序
        </h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Step number={1} title="保存客户端配置">
            PUT /google-oauth/config
          </Step>
          <Step number={2} title="生成授权链接">
            POST /email-accounts/&#123;id&#125;/google-oauth/prepare
          </Step>
          <Step number={3} title="自动完成回调">
            GET /google-oauth/callback 会校验邮箱并保存 Token
          </Step>
        </div>
      </Card>
      <Card className="space-y-4 p-5">
        <CodeBlock>{`PUT /api/v1/google-oauth/config
{
  "client_id": "<google client id>",
  "client_secret": "<google client secret>",
  "redirect_uri": "<origin>/api/v1/google-oauth/callback"
}`}</CodeBlock>
        <CodeBlock>{`POST /api/v1/email-accounts/1/google-oauth/prepare

// 返回 authorization_url；用户授权后 callback 会自动加密保存 refresh_token。`}</CodeBlock>
      </Card>
    </div>
  );
}
