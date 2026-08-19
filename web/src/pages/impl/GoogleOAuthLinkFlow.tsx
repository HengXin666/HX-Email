import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { IconAlertTriangle, IconCheck, IconLink, IconRefresh } from "../../components/icons";
import { Button } from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import type { GoogleOAuthFlowStatus, GoogleOAuthPrepareResult } from "../../types";
import { copyToClipboard } from "../../utils/clipboard";

interface GoogleOAuthLinkFlowProps {
  prepare: () => Promise<GoogleOAuthPrepareResult>;
  onAuthorized: (email: string) => void | Promise<void>;
  configReady: boolean;
  actionLabel?: string;
}

const POLL_INTERVAL_MS = 3000;
const POLL_MAX_ATTEMPTS = 200;

/**
 * Generate a Google authorization link, let the user copy it and open it in
 * any browser, then poll the backend until the callback completes.
 *
 * The link is never opened automatically: opening it in the current browser
 * would bind the Google session there, and the user may want to authorize in
 * a different browser or a logged-in account profile.
 */
export function GoogleOAuthLinkFlow({
  prepare,
  onAuthorized,
  configReady,
  actionLabel = "生成授权链接",
}: GoogleOAuthLinkFlowProps) {
  const { toast } = useToast();
  const [prepared, setPrepared] = useState<GoogleOAuthPrepareResult | null>(null);
  const [status, setStatus] = useState<GoogleOAuthFlowStatus | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const [completedEmail, setCompletedEmail] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const attemptsRef = useRef(0);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const checkStatus = useCallback(
    async (state: string): Promise<void> => {
      setIsChecking(true);
      try {
        const current = await api.getGoogleOAuthFlowStatus(state);
        setStatus(current);
        if (current.status === "done") {
          stopPolling();
          setCompletedEmail(current.email);
          toast(`${current.email} 授权成功，凭证已保存`, "success");
          await onAuthorized(current.email);
        } else if (current.status === "error" || current.status === "missing") {
          stopPolling();
          toast(current.error || "授权失败，请重新生成链接", "error");
        }
      } catch (error: unknown) {
        stopPolling();
        toast(error instanceof Error ? error.message : "查询授权状态失败", "error");
      } finally {
        setIsChecking(false);
      }
    },
    [onAuthorized, stopPolling, toast],
  );

  const startPolling = useCallback(
    (state: string): void => {
      stopPolling();
      attemptsRef.current = 0;
      pollRef.current = setInterval(() => {
        attemptsRef.current += 1;
        if (attemptsRef.current > POLL_MAX_ATTEMPTS) {
          stopPolling();
          toast("授权等待超时，请重新生成链接", "error");
          return;
        }
        void checkStatus(state);
      }, POLL_INTERVAL_MS);
    },
    [checkStatus, stopPolling, toast],
  );

  const handleGenerate = async (): Promise<void> => {
    setIsGenerating(true);
    try {
      const result = await prepare();
      setPrepared(result);
      setStatus({ status: "pending", email: "", error: "" });
      setCompletedEmail("");
      toast("授权链接已生成，请复制后在需要授权的浏览器中打开", "success");
      startPolling(result.state);
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "生成授权链接失败", "error");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleCheckNow = async (): Promise<void> => {
    if (!prepared) return;
    stopPolling();
    await checkStatus(prepared.state);
    if (!pollRef.current) startPolling(prepared.state);
  };

  const handleReset = (): void => {
    stopPolling();
    setPrepared(null);
    setStatus(null);
    setCompletedEmail("");
    attemptsRef.current = 0;
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          size="sm"
          onClick={handleGenerate}
          loading={isGenerating}
          disabled={!configReady}
        >
          {actionLabel}
        </Button>
        {!configReady && (
          <span className="inline-flex items-center gap-1 text-[11px] text-gh-text-secondary">
            <IconAlertTriangle size={11} className="text-gh-warning" />
            请先保存 Google OAuth 客户端配置
          </span>
        )}
      </div>

      {prepared && (
        <div className="rounded-lg border border-gh-accent/30 bg-gh-accent/5 p-3 space-y-2.5">
          <div className="text-xs font-semibold text-gh-text flex items-center gap-1.5">
            <IconLink size={13} className="text-gh-accent" />
            授权链接（请复制，不要直接打开）
          </div>
          <p className="text-[11px] leading-relaxed text-gh-text-secondary">
            在需要授权的浏览器中打开此链接并登录对应的 Google
            账号。完成后回到本页面，系统会自动检测并保存凭证。
          </p>
          <div className="flex items-center gap-2 rounded-md border border-gh-border bg-gh-canvas-inset px-3 py-2">
            <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-gh-text">
              {prepared.authorization_url}
            </span>
            <button
              type="button"
              onClick={() => {
                void copyToClipboard(prepared.authorization_url);
                toast("授权链接已复制", "success");
              }}
              className="shrink-0 rounded px-2 py-1 text-[11px] font-medium text-gh-accent hover:bg-gh-accent/10 transition-colors"
            >
              复制链接
            </button>
            <a
              href={prepared.authorization_url}
              target="_blank"
              rel="noreferrer"
              className="shrink-0 rounded px-2 py-1 text-[11px] font-medium text-gh-text-secondary hover:bg-gh-border/30 transition-colors"
            >
              新标签页打开
            </a>
          </div>

          {completedEmail ? (
            <div className="flex items-center justify-between gap-2 rounded-md border border-gh-success/30 bg-gh-success/5 px-3 py-2 text-xs text-gh-success">
              <span className="inline-flex items-center gap-1.5">
                <IconCheck size={13} /> {completedEmail} 授权成功，凭证已保存
              </span>
              <Button variant="ghost" size="sm" onClick={handleReset}>
                继续添加
              </Button>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-2 rounded-md border border-gh-border bg-gh-canvas-inset px-3 py-2">
              <span className="text-[11px] text-gh-text-secondary">
                {status?.status === "error"
                  ? "授权失败，请重新生成链接"
                  : "等待授权完成…（每 3 秒自动检测）"}
              </span>
              <Button variant="ghost" size="sm" onClick={handleCheckNow} loading={isChecking}>
                <IconRefresh size={12} className="mr-1 inline-block" />
                我已完成授权
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
