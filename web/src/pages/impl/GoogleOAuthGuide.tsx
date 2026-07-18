import React from "react";
import { IconAlertTriangle, IconCheck, IconCopy, IconLink } from "../../components/icons";
import { useToast } from "../../components/ui/Toast";
import { copyToClipboard } from "../../utils/clipboard";

const GOOGLE_MAIL_SCOPE = "https://mail.google.com/";

interface GoogleOAuthGuideProps {
  redirectUri: string;
  hasSavedConfig: boolean;
}

interface GuideStepProps {
  number: number;
  title: string;
  children: React.ReactNode;
  isComplete?: boolean;
}

function GuideStep({ number, title, children, isComplete = false }: GuideStepProps) {
  return (
    <details
      className="group rounded-md border border-gh-border bg-gh-canvas-inset"
      open={number === 1}
    >
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs font-medium text-gh-text transition-colors hover:bg-gh-border/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-gh-accent/60">
        <span
          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px] ${
            isComplete
              ? "border-gh-success/50 bg-gh-success/10 text-gh-success"
              : "border-gh-border bg-gh-canvas text-gh-text-muted"
          }`}
        >
          {isComplete ? <IconCheck size={11} /> : number}
        </span>
        <span className="flex-1">{title}</span>
        <span className="text-[10px] text-gh-text-secondary group-open:hidden">展开</span>
        <span className="hidden text-[10px] text-gh-text-secondary group-open:inline">收起</span>
      </summary>
      <div className="border-t border-gh-border px-3 py-2.5 text-xs leading-relaxed text-gh-text-secondary">
        {children}
      </div>
    </details>
  );
}

export function GoogleOAuthGuide({ redirectUri, hasSavedConfig }: GoogleOAuthGuideProps) {
  const { toast } = useToast();

  const handleCopy = async (value: string, label: string): Promise<void> => {
    const copied = await copyToClipboard(value);
    toast(copied ? `${label}已复制` : `${label}复制失败，请手动复制`, copied ? "success" : "error");
  };

  return (
    <div className="space-y-2" aria-label="Google OAuth 创建向导">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-semibold text-gh-text">创建 Google OAuth 客户端</div>
        <span className="rounded-full border border-gh-border px-2 py-0.5 text-[10px] text-gh-text-secondary">
          首次配置约 5 分钟
        </span>
      </div>

      <GuideStep number={1} title="1. 创建 Google Cloud 项目">
        <p>打开 Google Cloud，新建或选择一个专用于 HX Email 的项目。</p>
        <a
          href="https://console.cloud.google.com/projectcreate"
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-flex items-center gap-1 text-gh-accent hover:underline"
        >
          <IconLink size={11} /> 打开项目创建页
        </a>
      </GuideStep>

      <GuideStep number={2} title="2. 配置 Branding、Audience 和 Data Access">
        <ol className="list-decimal space-y-1 pl-4">
          <li>在 Google Auth Platform 填写应用名称和支持邮箱。</li>
          <li>个人 Gmail 选择 External；Testing 时把需要授权的 Gmail 加入 Test users。</li>
          <li>
            在 Data Access 添加 <code className="text-gh-text">openid</code>、
            <code className="text-gh-text">email</code> 和下方 Gmail Scope。
          </li>
        </ol>
        <div className="mt-2 flex items-center gap-2 rounded border border-gh-border bg-gh-canvas px-2 py-1.5">
          <code className="min-w-0 flex-1 truncate text-[11px] text-gh-accent">
            {GOOGLE_MAIL_SCOPE}
          </code>
          <button
            type="button"
            onClick={() => void handleCopy(GOOGLE_MAIL_SCOPE, "Gmail Scope")}
            className="inline-flex cursor-pointer items-center gap-1 rounded px-1.5 py-1 text-[11px] text-gh-text-muted transition-colors hover:bg-gh-border/40 hover:text-gh-text focus:outline-none focus-visible:ring-2 focus-visible:ring-gh-accent/60"
            aria-label="复制 Gmail Scope"
          >
            <IconCopy size={11} /> 复制
          </button>
        </div>
        <a
          href="https://console.cloud.google.com/auth/overview"
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-flex items-center gap-1 text-gh-accent hover:underline"
        >
          <IconLink size={11} /> 打开 Google Auth Platform
        </a>
      </GuideStep>

      <GuideStep number={3} title="3. 创建 Web application 客户端">
        <p>
          在 Clients 中创建 OAuth client，Application type 选择 Web
          application，并将下方地址原样加入 Authorized redirect URIs。
        </p>
        <div className="mt-2 flex items-center gap-2 rounded border border-gh-border bg-gh-canvas px-2 py-1.5">
          <code className="min-w-0 flex-1 break-all text-[11px] text-gh-accent">{redirectUri}</code>
          <button
            type="button"
            onClick={() => void handleCopy(redirectUri, "回调地址")}
            className="inline-flex cursor-pointer items-center gap-1 rounded px-1.5 py-1 text-[11px] text-gh-text-muted transition-colors hover:bg-gh-border/40 hover:text-gh-text focus:outline-none focus-visible:ring-2 focus-visible:ring-gh-accent/60"
            aria-label="复制回调地址"
          >
            <IconCopy size={11} /> 复制
          </button>
        </div>
        <a
          href="https://console.cloud.google.com/auth/clients"
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-flex items-center gap-1 text-gh-accent hover:underline"
        >
          <IconLink size={11} /> 打开 OAuth Clients
        </a>
      </GuideStep>

      <GuideStep number={4} title="4. 保存 Client ID / Secret 并授权" isComplete={hasSavedConfig}>
        <p>将创建结果填入下方并保存。随后点击“使用 Google 授权”，务必选择当前邮箱对应的账号。</p>
      </GuideStep>

      <div className="flex gap-2 rounded-md border border-gh-warning/40 bg-gh-warning/10 px-3 py-2 text-[11px] leading-relaxed text-gh-warning">
        <IconAlertTriangle size={13} className="mt-0.5 shrink-0" />
        <span>
          External + Testing 模式的邮件授权和 refresh token 会在 7 天后失效。长期运行需要切换到 In
          production；公开提供给其他用户时，Gmail Restricted Scope 还需要 Google 审核。
        </span>
      </div>
    </div>
  );
}
