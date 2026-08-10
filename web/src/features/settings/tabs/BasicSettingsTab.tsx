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
import { Button, Card, Input } from "../../../components/ui/Primitives";
import { useApp } from "../../../store/AppContext";
import { SectionHeader, SettingsTabFrame, SettingsToggle, TestResult } from "../SettingsControls";
import type { SettingsTabProps, TestOutcome } from "../types";
import { GoogleVerificationCard } from "./GoogleVerificationCard";

interface Announcement {
  title: string;
  body: string;
  html_url: string;
  latest_version: string;
  has_update: boolean;
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

export const BasicSettingsTab: React.FC<SettingsTabProps> = ({
  settings,
  setSetting,
  toast,
  user,
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
  const [hasUpdate, setHasUpdate] = useState(false);
  const [repositoryUrl, setRepositoryUrl] = useState("");
  const [isLoadingAnnouncement, setIsLoadingAnnouncement] = useState(false);
  const [announcement, setAnnouncement] = useState<Announcement | null>(null);

  useEffect(() => {
    void api
      .getVersionCheck()
      .then((result) => {
        setVersion(result.current_version || result.version || "");
        setHasUpdate(result.has_update);
        setRepositoryUrl(result.repository_url || "");
      })
      .catch(() => undefined);
    void api
      .getDeploymentInfo()
      .then((result) => {
        setPythonVersion(result.python_version);
        setPlatform(result.platform);
      })
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
        <SectionHeader>系统状态</SectionHeader>
        <div className="max-w-md space-y-2">
          <StatusRow icon={IconActivity} label="应用版本" value={version || "..."} />
          <StatusRow icon={IconServer} label="Python" value={pythonVersion || "..."} />
          <StatusRow icon={IconGlobe} label="平台" value={platform || "..."} />
          <StatusRow
            icon={IconDownload}
            label="版本更新"
            value={hasUpdate ? "有可用更新" : "已是最新"}
            color={hasUpdate ? "text-gh-warning" : "text-gh-success"}
          />
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
    </SettingsTabFrame>
  );
};
