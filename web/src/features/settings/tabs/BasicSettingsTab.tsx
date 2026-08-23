import type React from "react";
import { useEffect, useState } from "react";
import { api } from "../../../api/client";
import {
  IconActivity,
  IconCheck,
  IconCode,
  IconDownload,
  IconGlobe,
  IconKey,
  IconServer,
  IconZap,
} from "../../../components/icons";
import { ConfirmModal } from "../../../components/ui/ConfirmModal";
import { Button, Card, Input } from "../../../components/ui/Primitives";
import { Spinner } from "../../../components/ui/Spinner";
import { useApp } from "../../../store/AppContext";
import { formatRelativeTime } from "../../../utils/time";
import { SectionHeader, SettingsTabFrame, SettingsToggle, TestResult } from "../SettingsControls";
import type { SettingsTabProps, TestOutcome } from "../types";
import { GlobalRefreshCard } from "./GlobalRefreshCard";
import { GoogleVerificationCard } from "./GoogleVerificationCard";

interface Announcement {
  title: string;
  body: string;
  html_url: string;
  current_version: string;
  latest_version: string;
  has_update: boolean;
}

interface UpdateStatus {
  enabled: boolean;
  available: boolean;
  available_reason: string;
  running: boolean;
  phase: string;
  success: boolean | null;
  message: string;
  output: string;
  target_version: string;
  started_at: string;
  finished_at: string;
  last_update: { success?: boolean; version?: string; finished_at?: string };
}

interface StatusRowProps {
  icon: React.FC<{ size?: number; className?: string }>;
  label: string;
  value: string;
  color?: string;
}

const StatusRow: React.FC<StatusRowProps> = ({
  icon: Icon,
  label,
  value,
  color = "text-gh-text",
}) => (
  <div className="flex items-center justify-between rounded-md border border-gh-border bg-gh-canvas-inset px-3 py-2">
    <span className="flex items-center gap-2 text-sm text-gh-text">
      <Icon size={12} className="text-gh-text-muted" /> {label}
    </span>
    <span className={`text-xs ${color}`}>{value}</span>
  </div>
);

const displayVersion = (value: string): string => `v${value.replace(/^v/i, "")}`;

export const BasicSettingsTab: React.FC<SettingsTabProps> = ({
  settings,
  setSetting,
  toast,
  user,
  accounts,
}) => {
  const { updateCredentials } = useApp();
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSavingPassword, setIsSavingPassword] = useState(false);
  const [isTestingAI, setIsTestingAI] = useState(false);
  const [aiResult, setAiResult] = useState<TestOutcome | null>(null);
  const [isAPIKeyVisible, setIsAPIKeyVisible] = useState(false);
  const [version, setVersion] = useState("");
  const [pythonVersion, setPythonVersion] = useState("");
  const [platform, setPlatform] = useState("");
  const [repositoryUrl, setRepositoryUrl] = useState("");
  const [isLoadingAnnouncement, setIsLoadingAnnouncement] = useState(false);
  const [announcement, setAnnouncement] = useState<Announcement | null>(null);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null);
  const [isUpdateDialogOpen, setIsUpdateDialogOpen] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);

  useEffect(() => {
    void api
      .getVersionCheck()
      .then((result) => {
        setVersion(result.current_version || result.version || "");
        setRepositoryUrl(result.repository_url || "");
        setAnnouncement({
          title: result.title || result.latest_version || result.current_version,
          body: result.body || "",
          html_url: result.html_url || "",
          current_version: result.current_version,
          latest_version: result.latest_version || result.current_version,
          has_update: result.has_update,
        });
      })
      .catch(() => undefined);
    void api
      .getDeploymentInfo()
      .then((result) => {
        setPythonVersion(result.python_version);
        setPlatform(result.platform);
      })
      .catch(() => undefined);
    void api
      .getUpdateStatus()
      .then(setUpdateStatus)
      .catch(() => undefined);
  }, []);

  const handlePasswordSave = async (): Promise<void> => {
    if (!newPassword || newPassword !== confirmPassword || !user) {
      toast(!newPassword ? "请输入新密码" : "两次密码不一致", "error");
      return;
    }
    setIsSavingPassword(true);
    try {
      await updateCredentials(user.username, newPassword);
      setNewPassword("");
      setConfirmPassword("");
      toast("密码已更新", "success");
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "密码更新失败", "error");
    } finally {
      setIsSavingPassword(false);
    }
  };

  const handleAITest = async (): Promise<void> => {
    setIsTestingAI(true);
    setAiResult(null);
    try {
      const result = await api.testVerificationAI({
        base_url: settings.verification_ai_base_url || undefined,
        model_id: settings.verification_ai_model || undefined,
        api_key: settings.verification_ai_api_key || undefined,
      });
      setAiResult({
        success: result.success,
        message: result.message || (result.code ? `Code: ${result.code}` : "已测试"),
      });
    } catch (error: unknown) {
      setAiResult({
        success: false,
        message: error instanceof Error ? error.message : "AI 测试失败",
      });
    } finally {
      setIsTestingAI(false);
    }
  };

  const handleAnnouncement = async (): Promise<void> => {
    setIsLoadingAnnouncement(true);
    try {
      const result = await api.getUpdateAnnouncement();
      setAnnouncement(result);
      toast(result.success ? "已获取最新公告" : result.title, result.success ? "success" : "info");
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "获取更新公告失败", "error");
    } finally {
      setIsLoadingAnnouncement(false);
    }
  };

  const startUpdate = async (): Promise<void> => {
    if (!announcement) return;
    setIsUpdateDialogOpen(false);
    setIsUpdating(true);
    try {
      await api.applyUpdate(announcement.latest_version);
      toast("更新已启动，正在拉取新镜像…", "info");
      pollUpdateStatus();
    } catch (error: unknown) {
      setIsUpdating(false);
      toast(error instanceof Error ? error.message : "启动更新失败", "error");
    }
  };

  const pollUpdateStatus = (): void => {
    window.setTimeout(async () => {
      try {
        const status = await api.getUpdateStatus();
        setUpdateStatus(status);
        if (status.running) {
          pollUpdateStatus();
          return;
        }
        setIsUpdating(false);
        if (status.success) {
          toast("更新完成，页面即将刷新", "success");
          window.setTimeout(() => window.location.reload(), 1500);
        } else {
          toast(status.message || "更新失败", "error");
        }
      } catch {
        // 更新过程中容器会被重建, 连接短暂中断: 等待服务恢复后重载页面
        window.setTimeout(() => window.location.reload(), 5000);
      }
    }, 2000);
  };

  return (
    <SettingsTabFrame tabKey="basic">
      <Card className="p-5">
        <SectionHeader>登录密码</SectionHeader>
        <div className="max-w-md space-y-3">
          <Input
            label="新密码"
            type="password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
          />
          <Input
            label="确认密码"
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
          />
          <Button variant="primary" onClick={handlePasswordSave} loading={isSavingPassword}>
            更新密码
          </Button>
        </div>
      </Card>

      {user?.is_admin && <GoogleVerificationCard toast={toast} />}

      {user?.is_admin && (
        <Card className="p-5">
          <SectionHeader>验证码 AI</SectionHeader>
          <div className="max-w-lg space-y-3">
            <div className="flex items-center justify-between rounded-md border border-gh-border bg-gh-canvas-inset p-3">
              <div>
                <div className="text-sm text-gh-text">启用验证码 AI</div>
                <div className="text-xs text-gh-text-secondary">自动识别验证邮件中的验证码</div>
              </div>
              <SettingsToggle
                enabled={settings.verification_ai_enabled === "true"}
                onChange={(value) =>
                  setSetting("verification_ai_enabled", value ? "true" : "false")
                }
              />
            </div>
            <Input
              label="Base URL"
              value={settings.verification_ai_base_url || ""}
              onChange={(event) => setSetting("verification_ai_base_url", event.target.value)}
              placeholder="https://api.openai.com/v1"
            />
            <Input
              label="Model ID"
              value={settings.verification_ai_model || ""}
              onChange={(event) => setSetting("verification_ai_model", event.target.value)}
              placeholder="gpt-4o-mini"
            />
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <Input
                  label="API Key"
                  type={isAPIKeyVisible ? "text" : "password"}
                  value={settings.verification_ai_api_key || ""}
                  onChange={(event) => setSetting("verification_ai_api_key", event.target.value)}
                />
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsAPIKeyVisible((value) => !value)}
              >
                {isAPIKeyVisible ? <IconCheck size={13} /> : <IconKey size={13} />}
              </Button>
              <Button variant="secondary" size="sm" onClick={handleAITest} loading={isTestingAI}>
                <IconZap size={13} /> 测试
              </Button>
            </div>
            <TestResult result={aiResult} />
          </div>
        </Card>
      )}

      <Card className="p-5">
        <SectionHeader>凭证刷新（OAuth token）</SectionHeader>
        <div className="max-w-lg space-y-3">
          <div className="rounded-md border border-gh-border bg-gh-canvas-inset p-3 text-xs text-gh-text-secondary">
            批量刷新（全部/失败/分组/快速巡查）按账号<b>随机错峰</b>：每账号随机延迟 1..N
            秒后再刷新，避免同批秒级连刷被微软风控引擎聚类标记为 compromised（security interrupt for
            collecting proof，20260823 实测： 4 个账号同一刷新批次 3 秒内同时被标）。
          </div>
          <Input
            label="批量刷新错峰上限（秒，0 = 关闭错峰）"
            type="number"
            value={settings.refresh_stagger_max_seconds ?? "20"}
            onChange={(event) => setSetting("refresh_stagger_max_seconds", event.target.value)}
          />
          <Input
            label="全局刷新并发数（1..64，默认 8）"
            type="number"
            min="1"
            max="64"
            value={settings.refresh_concurrent_workers ?? "8"}
            onChange={(event) => setSetting("refresh_concurrent_workers", event.target.value)}
          />
          <GlobalRefreshCard toast={toast} />
          <div className="flex items-center justify-between rounded-md border border-gh-border bg-gh-canvas-inset p-3">
            <div>
              <div className="text-sm text-gh-text">后台定时随机刷新</div>
              <div className="text-xs text-gh-text-secondary">
                平台按周期自动刷新全部账号 token（错峰执行），巡检只读状态
              </div>
            </div>
            <SettingsToggle
              enabled={settings.refresh_schedule_enabled === "true"}
              onChange={(value) => setSetting("refresh_schedule_enabled", value ? "true" : "false")}
            />
          </div>
          <Input
            label="定时刷新间隔（秒，60..86400，默认 3600）"
            type="number"
            value={settings.refresh_schedule_interval_seconds ?? "3600"}
            onChange={(event) =>
              setSetting("refresh_schedule_interval_seconds", event.target.value)
            }
          />
          <div>
            <div className="mb-2 text-sm text-gh-text">最近刷新时间（按最近刷新排序）</div>
            <div className="max-h-60 divide-y divide-gh-border overflow-y-auto rounded-md border border-gh-border">
              {[...(accounts || [])]
                .filter((a) => a.last_refresh_at || a.refresh_failed_at)
                .sort((a, b) =>
                  (b.last_refresh_at || b.refresh_failed_at || "").localeCompare(
                    a.last_refresh_at || a.refresh_failed_at || "",
                  ),
                )
                .slice(0, 12)
                .map((a) => (
                  <div
                    key={a.id}
                    className="flex items-center justify-between gap-2 px-3 py-1.5 text-xs"
                  >
                    <span className="truncate font-mono text-gh-text">{a.primary_address}</span>
                    <span
                      className={
                        a.refresh_failed_at
                          ? "shrink-0 text-gh-warning"
                          : "shrink-0 text-gh-success"
                      }
                    >
                      {a.refresh_failed_at
                        ? `失败于 ${formatRelativeTime(a.refresh_failed_at)}`
                        : a.last_refresh_at
                          ? `刷新于 ${formatRelativeTime(a.last_refresh_at)}`
                          : "从未刷新"}
                    </span>
                  </div>
                ))}
              {(accounts || []).filter((a) => a.last_refresh_at || a.refresh_failed_at).length ===
                0 && <div className="px-3 py-2 text-xs text-gh-text-secondary">暂无刷新记录</div>}
            </div>
          </div>
        </div>
      </Card>

      <Card className="p-5">
        <SectionHeader>系统状态</SectionHeader>
        <div className="max-w-md space-y-2">
          <StatusRow icon={IconActivity} label="应用版本" value={version || "..."} />
          <StatusRow icon={IconServer} label="Python" value={pythonVersion || "..."} />
          <StatusRow icon={IconGlobe} label="平台" value={platform || "..."} />
          <StatusRow
            icon={IconDownload}
            label="版本更新"
            value={announcement?.has_update ? "有可用更新" : "已是最新"}
            color={announcement?.has_update ? "text-gh-warning" : "text-gh-success"}
          />
          {updateStatus?.last_update?.success && (
            <StatusRow
              icon={IconCheck}
              label="上次更新"
              value={`${displayVersion(updateStatus.last_update.version || "")} ${
                updateStatus.last_update.finished_at || ""
              }`}
              color="text-gh-success"
            />
          )}
          {announcement?.has_update && (
            <div className="rounded-md border border-gh-warning/40 bg-gh-warning/10 p-3">
              <div className="text-sm font-medium text-gh-warning">
                发现新版本 {displayVersion(announcement.latest_version)}
              </div>
              <div className="mt-1 text-xs text-gh-text-secondary">
                当前版本 v{announcement.current_version || version} · {announcement.title}
              </div>
              {updateStatus && !updateStatus.available && (
                <div className="mt-2 text-xs text-gh-text-secondary">
                  {updateStatus.available_reason}
                </div>
              )}
              {!isUpdating && updateStatus?.available && (
                <Button
                  variant="primary"
                  size="sm"
                  className="mt-2"
                  onClick={() => setIsUpdateDialogOpen(true)}
                >
                  <IconDownload size={13} /> 立即更新
                </Button>
              )}
              {isUpdating && (
                <div className="mt-2 flex items-center gap-2 text-xs text-gh-text-secondary">
                  <Spinner size={14} />
                  {updateStatus?.phase ? `正在更新（${updateStatus.phase}）…` : "正在更新…"}
                </div>
              )}
            </div>
          )}
          {repositoryUrl && (
            <StatusRow
              icon={IconCode}
              label="项目仓库"
              value={repositoryUrl.replace("https://github.com/", "")}
            />
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={handleAnnouncement}
            loading={isLoadingAnnouncement}
          >
            <IconDownload size={13} /> 获取更新公告
          </Button>
          {announcement && (
            <div className="rounded-md border border-gh-border bg-gh-canvas-inset p-3 text-sm">
              <div className="font-medium text-gh-text">
                {announcement.title || announcement.latest_version}
              </div>
              {announcement.body && (
                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap font-sans text-xs text-gh-text-secondary">
                  {announcement.body}
                </pre>
              )}
              {announcement.html_url && (
                <a
                  href={announcement.html_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-flex text-xs text-gh-accent hover:underline"
                >
                  查看发布页
                </a>
              )}
            </div>
          )}
        </div>
      </Card>
      <ConfirmModal
        open={isUpdateDialogOpen}
        title={`更新到 ${displayVersion(announcement?.latest_version ?? "")}`}
        message="将自动拉取最新镜像并重建容器，服务会短暂中断（约 10~60 秒），更新期间请勿关闭页面。是否继续？"
        confirmLabel="确认更新"
        loading={isUpdating}
        onConfirm={() => void startUpdate()}
        onCancel={() => setIsUpdateDialogOpen(false)}
      />
    </SettingsTabFrame>
  );
};
