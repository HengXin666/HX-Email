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
          <Step number={1} title="无需填写邮箱">
            新增 Gmail 时不用手动输入邮箱：生成授权链接后，在任意浏览器打开并登录对应的 Google
            账号，系统会从 Google 自动读取邮箱。
          </Step>
          <Step number={2} title="配置 Google Cloud OAuth 客户端">
            按页面向导创建 Web application，保存 Client ID、Secret 和完全一致的回调地址。
          </Step>
          <Step number={3} title="复制链接并授权">
            授权链接不会被自动打开：复制后在需要授权的浏览器（或当前浏览器的其他标签页）中访问并同意邮件权限。
          </Step>
          <Step number={4} title="自动持久化">
            回调会校验账号身份，把 Refresh Token 加密写入自动创建（或更新）的 Gmail
            账号，无需复制粘贴。
          </Step>
        </div>
      </Card>
      <Card className="p-5">
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-gh-text">
          <IconCheck size={14} /> 持久化与安全
        </h2>
        <div className="space-y-3 text-sm leading-relaxed text-gh-text-secondary">
          <p>Google Client Secret 和 Refresh Token 均加密保存，页面不会回显。</p>
          <p>已有 Gmail 重新授权时，授权账号必须与本地地址一致，避免 Token 绑错账号。</p>
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
            POST /google-oauth/prepare（新增账号，无需邮箱）或 POST
            /email-accounts/&#123;id&#125;/google-oauth/prepare（已有账号）
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
        <CodeBlock>{`POST /api/v1/google-oauth/prepare
// 新增 Gmail：无需传邮箱，授权回调自动创建账号
// 可选 ?group_id=<id> 指定分组

GET /api/v1/google-oauth/flow/<state>/status
// 轮询授权完成状态：{"status":"pending|done|error|missing","email":"...","error":"..."}`}</CodeBlock>
      </Card>
    </div>
  );
}
