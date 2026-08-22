import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, subscribePatrol } from "../../api/client";
import { IconPause, IconPlay, IconRefresh, IconSquare, IconX } from "../../components/icons";
import { useToast } from "../../components/ui/Toast";
import type { PatrolSnapshot, PatrolStreamEvent } from "../../types";
import { formatRelativeTime } from "../../utils/time";

const RUNNING_STATES = new Set(["starting", "running", "paused", "stopping"]);

const STATUS_LABELS: Record<string, string> = {
  idle: "空闲",
  starting: "启动中",
  running: "进行中",
  paused: "已暂停",
  stopping: "终止中",
  done: "已完成",
  error: "出错",
  stopped: "已终止",
};

/**
 * 持久化巡检面板: 刷新/切换页面不丢失状态, 支持暂停/恢复/终止。
 *
 * 巡检在服务端后台线程执行; 本组件挂载时先查状态, 若进行中则订阅 SSE 事件流
 * (自动重连 + 服务端回放缓冲事件补全进度), 终态后订阅自动结束。
 */
export const PatrolPanel: React.FC = () => {
  const { toast } = useToast();
  const [snapshot, setSnapshot] = useState<PatrolSnapshot | null>(null);
  const [starting, setStarting] = useState(false);
  const [acting, setActing] = useState(false);
  const subscribingRef = useRef(false);

  const refreshStatus = useCallback(async (): Promise<void> => {
    try {
      setSnapshot(await api.patrolStatus());
    } catch (err: any) {
      toast(err.message, "error");
    }
  }, [toast]);

  const handleStreamEvent = useCallback((event: PatrolStreamEvent): void => {
    if (event.type === "status") {
      setSnapshot(event as PatrolSnapshot);
    } else if (event.type === "start") {
      setSnapshot((prev) =>
        prev ? { ...prev, status: "running", total: event.total ?? prev.total } : prev,
      );
    } else if (event.type === "progress") {
      setSnapshot((prev) =>
        prev
          ? {
              ...prev,
              status: "running",
              current: event.current ?? prev.current,
              total: event.total ?? prev.total,
              email: event.email ?? prev.email,
            }
          : prev,
      );
    } else if (event.type === "complete") {
      setSnapshot((prev) =>
        prev
          ? {
              ...prev,
              status: event.error ? "error" : event.stopped ? "stopped" : "done",
              current: event.total ?? prev.current,
              total: event.total ?? prev.total,
              success: typeof event.success === "number" ? event.success : prev.success,
              failed: event.failed ?? prev.failed,
            }
          : prev,
      );
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void refreshStatus().then(() => {
      if (cancelled || subscribingRef.current) return;
      // 挂载时若已有巡检进行中, 立即订阅补全进度
      void subscribePatrol((event) => {
        if (!cancelled) handleStreamEvent(event);
      }).catch(() => {
        /* 订阅失败不阻塞页面 */
      });
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startPatrol = async (): Promise<void> => {
    setStarting(true);
    try {
      const result = await api.patrolStart({ mode: "all" });
      setSnapshot(result.snapshot);
      subscribingRef.current = true;
      void subscribePatrol(handleStreamEvent).catch(() => {
        /* 重连逻辑在 subscribePatrol 内部 */
      });
    } catch (err: any) {
      toast(err.message, "error");
      await refreshStatus();
    } finally {
      setStarting(false);
    }
  };

  const runAction = async (
    action: "pause" | "resume" | "stop",
    successMessage: string,
  ): Promise<void> => {
    setActing(true);
    try {
      const result =
        action === "pause"
          ? await api.patrolPause()
          : action === "resume"
            ? await api.patrolResume()
            : await api.patrolStop();
      setSnapshot(result.snapshot);
      if (result.success) toast(successMessage, "success");
    } catch (err: any) {
      toast(err.message, "error");
    } finally {
      setActing(false);
    }
  };

  const running = snapshot !== null && RUNNING_STATES.has(snapshot.status);
  const paused = snapshot?.status === "paused";
  const pct =
    snapshot && snapshot.total > 0
      ? Math.min(100, Math.round((snapshot.current / snapshot.total) * 100))
      : 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-gh-text">
          <IconRefresh
            size={14}
            className={running ? "text-gh-accent animate-spin" : "text-gh-text-muted"}
          />
          {snapshot ? (STATUS_LABELS[snapshot.status] ?? snapshot.status) : "查询中..."}
          {snapshot?.mode_label ? (
            <span className="text-xs font-normal text-gh-text-secondary">
              ({snapshot.mode_label})
            </span>
          ) : null}
        </div>
        <button
          onClick={() => void refreshStatus()}
          className="p-1 rounded-md text-gh-text-muted hover:text-gh-accent hover:bg-gh-accent/10 transition-colors"
          title="刷新状态"
        >
          <IconX size={13} className="rotate-45" />
        </button>
      </div>

      {snapshot && snapshot.status !== "idle" && (
        <div className="space-y-1.5 rounded-md border border-gh-border bg-gh-canvas-inset p-2.5">
          <div className="flex items-center justify-between text-xs">
            <span className="text-gh-text-secondary tabular-nums">
              {snapshot.current}/{snapshot.total}
              {snapshot.email ? ` · ${snapshot.email}` : ""}
            </span>
            <span className="flex items-center gap-2 tabular-nums">
              <span className="text-gh-success">成功 {snapshot.success}</span>
              <span className="text-gh-danger">失败 {snapshot.failed}</span>
            </span>
          </div>
          <div className="h-1.5 bg-gh-canvas rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${pct}%`,
                background:
                  snapshot.status === "error" || snapshot.status === "stopped"
                    ? "var(--gh-danger, #f85149)"
                    : "linear-gradient(90deg, #3fb950, #58a6ff)",
              }}
            />
          </div>
          {snapshot.started_at && (
            <div className="text-[10px] text-gh-text-muted">
              开始于 {formatRelativeTime(snapshot.started_at)}
              {snapshot.finished_at ? ` · 结束于 ${formatRelativeTime(snapshot.finished_at)}` : ""}
            </div>
          )}
          {snapshot.error && (
            <div className="text-[11px] text-gh-danger break-all">{snapshot.error}</div>
          )}
        </div>
      )}

      <div className="flex items-center gap-1.5">
        <button
          onClick={() => void startPatrol()}
          disabled={running || starting}
          className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium text-gh-accent bg-gh-accent/10 border border-gh-accent/30 hover:bg-gh-accent/20 transition-colors disabled:opacity-40"
          title="批量刷新全部 OAuth 账号 Token"
        >
          <IconRefresh size={13} className={starting ? "animate-spin" : ""} />
          巡查全部
        </button>
        {running && (
          <button
            onClick={() =>
              void runAction(paused ? "resume" : "pause", paused ? "已恢复" : "已暂停")
            }
            disabled={acting}
            className="inline-flex items-center justify-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium text-gh-warning bg-gh-warning/10 border border-gh-warning/30 hover:bg-gh-warning/20 transition-colors disabled:opacity-40"
            title={paused ? "恢复巡检" : "暂停巡检"}
          >
            {paused ? <IconPlay size={13} /> : <IconPause size={13} />}
            {paused ? "恢复" : "暂停"}
          </button>
        )}
        {running && (
          <button
            onClick={() => void runAction("stop", "已终止巡检")}
            disabled={acting}
            className="inline-flex items-center justify-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium text-gh-danger bg-gh-danger/10 border border-gh-danger/30 hover:bg-gh-danger/20 transition-colors disabled:opacity-40"
            title="终止巡检"
          >
            <IconSquare size={12} />
            终止
          </button>
        )}
      </div>
      <p className="text-[11px] text-gh-text-muted leading-relaxed">
        巡检在后台执行, 刷新页面或切换页面不会中断; 可随时回到本页查看进度、暂停或终止。
      </p>
    </div>
  );
};
