import { useEffect, useRef, useState } from "react";
import { api } from "../../../api/client";
import { IconPlay, IconSquare } from "../../../components/icons";
import { Button, Card } from "../../../components/ui/Primitives";
import { Spinner } from "../../../components/ui/Spinner";
import type { PatrolSnapshot } from "../../../types";
import { formatRelativeTime } from "../../../utils/time";

interface GlobalRefreshCardProps {
  toast: (message: string, tone?: "success" | "error" | "info") => void;
}

interface ProgressState {
  status: string;
  total: number;
  current: number;
  success: number;
  failed: number;
  email: string;
  started_at: string | null;
  finished_at: string | null;
  error: string;
  mode_label: string;
}

const RUNNING_STATES = new Set(["starting", "running", "paused", "stopping"]);

const emptyProgress: ProgressState = {
  status: "idle",
  total: 0,
  current: 0,
  success: 0,
  failed: 0,
  email: "",
  started_at: null,
  finished_at: null,
  error: "",
  mode_label: "",
};

const toProgress = (snapshot: PatrolSnapshot | null | undefined): ProgressState => {
  if (!snapshot) return emptyProgress;
  return {
    status: snapshot.status ?? "idle",
    total: snapshot.total ?? 0,
    current: snapshot.current ?? 0,
    success: snapshot.success ?? 0,
    failed: snapshot.failed ?? 0,
    email: snapshot.email ?? "",
    started_at: snapshot.started_at ?? null,
    finished_at: snapshot.finished_at ?? null,
    error: snapshot.error ?? "",
    mode_label: snapshot.mode_label ?? "",
  };
};

export const GlobalRefreshCard: React.FC<GlobalRefreshCardProps> = ({ toast }) => {
  const [progress, setProgress] = useState<ProgressState>(emptyProgress);
  const [starting, setStarting] = useState(false);
  const pollRef = useRef<number | null>(null);
  const running = RUNNING_STATES.has(progress.status);

  const pollStatus = async (): Promise<void> => {
    try {
      const snapshot = await api.patrolStatus();
      setProgress(toProgress(snapshot));
    } catch {
      // 轮询失败保持现状, 下一轮再试
    }
  };

  useEffect(() => {
    void pollStatus();
    pollRef.current = window.setInterval(() => void pollStatus(), 3000);
    return () => {
      if (pollRef.current !== null) window.clearInterval(pollRef.current);
    };
  }, []);

  const handleStart = async (): Promise<void> => {
    setStarting(true);
    try {
      const result = await api.patrolStart({ mode: "all" });
      setProgress(toProgress(result.snapshot));
      toast("已启动全局凭证刷新（后台执行，可随时刷新页面查看进度）", "info");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "启动刷新失败";
      toast(msg, "error");
    } finally {
      setStarting(false);
    }
  };

  const handleStop = async (): Promise<void> => {
    try {
      const result = await api.patrolStop();
      setProgress(toProgress(result.snapshot));
      toast("已请求停止刷新", "info");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "停止刷新失败";
      toast(msg, "error");
    }
  };

  const percent: number =
    progress.total > 0 ? Math.min(100, Math.round((progress.current / progress.total) * 100)) : 0;

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm text-gh-text">立即全局刷新凭证</div>
          <div className="text-xs text-gh-text-secondary">
            后台并发刷新全部活跃 OAuth 账号（可在账号页查看实时进度）
          </div>
        </div>
        <div className="flex items-center gap-2">
          {running ? (
            <Button variant="danger" size="sm" onClick={() => void handleStop()}>
              <IconSquare size={13} /> 停止
            </Button>
          ) : (
            <Button
              variant="primary"
              size="sm"
              onClick={() => void handleStart()}
              loading={starting}
            >
              <IconPlay size={13} /> 立即刷新
            </Button>
          )}
        </div>
      </div>

      {running && (
        <div className="mt-3 space-y-2">
          <div className="flex items-center gap-2 text-xs text-gh-text-secondary">
            <Spinner size={14} />
            <span>
              {progress.mode_label || "全部"}刷新中：{progress.current}/{progress.total}（成功{" "}
              {progress.success}，失败 {progress.failed}）
            </span>
            {progress.email && (
              <span className="max-w-56 truncate font-mono">{progress.email}</span>
            )}
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-gh-canvas-inset">
            <div
              className="h-full rounded-full bg-gh-primary transition-all duration-500"
              style={{ width: `${percent}%` }}
            />
          </div>
          <div className="text-right text-[11px] text-gh-text-muted">{percent}%</div>
        </div>
      )}

      {!running && progress.status !== "idle" && (
        <div className="mt-3 text-xs">
          {progress.status === "done" && (
            <span className="text-gh-success">
              上次完成：成功 {progress.success}，失败 {progress.failed}（共 {progress.total}）
              {progress.finished_at ? `，${formatRelativeTime(progress.finished_at)}` : ""}
            </span>
          )}
          {progress.status === "error" && (
            <span className="text-gh-danger">
              上次失败：{progress.error || "未知错误"}
              {progress.finished_at ? `，${formatRelativeTime(progress.finished_at)}` : ""}
            </span>
          )}
          {progress.status === "stopped" && (
            <span className="text-gh-warning">
              已停止：完成 {progress.current}/{progress.total}（成功 {progress.success}，失败{" "}
              {progress.failed}）
            </span>
          )}
        </div>
      )}

      {!running && progress.status === "idle" && (
        <div className="mt-3 text-xs text-gh-text-secondary">当前无进行中的刷新任务</div>
      )}
    </Card>
  );
};
