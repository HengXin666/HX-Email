import type React from "react";
import { useState } from "react";
import { api } from "../../../api/client";
import { IconMail } from "../../../components/icons";
import { Button, Card, Input } from "../../../components/ui/Primitives";
import { SectionHeader, TestResult, ToggleRow } from "../SettingsControls";
import type { SettingsTabProps, TestOutcome } from "../types";

export const EmailForwardingCard: React.FC<SettingsTabProps> = ({
  settings,
  setSetting,
  toast,
}) => {
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestOutcome | null>(null);

  const applyPreset = (host: string): void => {
    setSetting("email_notification_smtp_host", host);
    setSetting("email_notification_smtp_port", "587");
  };

  const handleTest = async (): Promise<void> => {
    const recipient: string = settings.email_notification_recipient || "";
    const host: string = settings.email_notification_smtp_host || "";
    const port: number = Number(settings.email_notification_smtp_port || "587");
    if (!recipient || !host) {
      toast("请填写收件邮箱和 SMTP 主机", "error");
      return;
    }
    setIsTesting(true);
    setTestResult(null);
    try {
      const result = await api.testEmail({
        recipient,
        smtp_host: host,
        smtp_port: Number.isFinite(port) ? port : 587,
        smtp_user: settings.email_notification_smtp_user || undefined,
        smtp_password: settings.email_notification_smtp_password || undefined,
      });
      setTestResult({
        success: result.success,
        message: result.message || result.error || "邮件测试完成",
      });
    } catch (error: unknown) {
      setTestResult({
        success: false,
        message: error instanceof Error ? error.message : "邮件测试失败",
      });
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <Card className="p-5">
      <SectionHeader>邮件转发</SectionHeader>
      <div className="max-w-lg space-y-3">
        <ToggleRow
          label="收到新邮件后转发"
          description="通过 SMTP 将新邮件正文转发到指定邮箱"
          enabled={settings.email_notification_enabled === "true"}
          onChange={(value) => setSetting("email_notification_enabled", value ? "true" : "false")}
        />
        <Input
          label="转发到"
          type="email"
          value={settings.email_notification_recipient || ""}
          onChange={(event) => setSetting("email_notification_recipient", event.target.value)}
          placeholder="archive@example.com"
        />
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="SMTP 预设">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => applyPreset("smtp.gmail.com")}
          >
            Gmail
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => applyPreset("smtp-mail.outlook.com")}
          >
            Outlook
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => applyPreset("smtp.qq.com")}
          >
            QQ
          </Button>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_120px]">
          <Input
            label="SMTP 主机"
            value={settings.email_notification_smtp_host || ""}
            onChange={(event) => setSetting("email_notification_smtp_host", event.target.value)}
            placeholder="smtp.gmail.com"
          />
          <Input
            label="端口"
            type="number"
            value={settings.email_notification_smtp_port || "587"}
            onChange={(event) => setSetting("email_notification_smtp_port", event.target.value)}
          />
        </div>
        <Input
          label="SMTP 用户"
          type="email"
          value={settings.email_notification_smtp_user || ""}
          onChange={(event) => setSetting("email_notification_smtp_user", event.target.value)}
        />
        <Input
          label="SMTP 密码 / 授权码"
          type="password"
          value={settings.email_notification_smtp_password || ""}
          onChange={(event) => setSetting("email_notification_smtp_password", event.target.value)}
        />
        <Button variant="secondary" size="sm" onClick={handleTest} loading={isTesting}>
          <IconMail size={13} /> 测试发送
        </Button>
        <TestResult result={testResult} />
      </div>
    </Card>
  );
};
