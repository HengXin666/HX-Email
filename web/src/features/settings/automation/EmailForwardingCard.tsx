import type React from "react";
import { useMemo, useState } from "react";
import { api } from "../../../api/client";
import { IconMail } from "../../../components/icons";
import { Button, Card, Input, Select } from "../../../components/ui/Primitives";
import { SectionHeader, TestResult, ToggleRow } from "../SettingsControls";
import type { SettingsTabProps, TestOutcome } from "../types";

interface SenderAccountOption {
  value: string;
  label: string;
}

const getSenderAccountOptions = (accounts: SettingsTabProps["accounts"]): SenderAccountOption[] =>
  accounts
    .filter((account) => account.status === "active" && account.primary_address)
    .map((account) => ({
      value: String(account.id),
      label: [account.primary_address, account.display_name, account.provider]
        .filter(Boolean)
        .join(" · "),
    }))
    .sort((left, right) => left.label.localeCompare(right.label));

export const EmailForwardingCard: React.FC<SettingsTabProps> = ({
  settings,
  setSetting,
  toast,
  accounts,
}) => {
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestOutcome | null>(null);
  const senderAccountOptions: SenderAccountOption[] = useMemo(
    () => getSenderAccountOptions(accounts),
    [accounts],
  );
  const senderAccountId: string = settings.email_notification_account_id || "";
  const recipient: string = settings.email_notification_recipient || "";
  const selectedSenderAccountId: string = senderAccountOptions.some(
    (option) => option.value === senderAccountId,
  )
    ? senderAccountId
    : "";

  const applyPreset = (host: string): void => {
    setSetting("email_notification_smtp_host", host);
    setSetting("email_notification_smtp_port", "587");
  };

  const handleTest = async (): Promise<void> => {
    const recipient: string = settings.email_notification_recipient || "";
    const senderAccountId: string = settings.email_notification_account_id || "";
    const host: string = settings.email_notification_smtp_host || "";
    const port: number = Number(settings.email_notification_smtp_port || "587");
    const smtpOverride: Record<string, unknown> = host
      ? {
          smtp_host: host,
          smtp_port: Number.isFinite(port) ? port : 587,
        }
      : {};
    if (!recipient) {
      toast("请填写转发目标邮箱", "error");
      return;
    }
    if (!senderAccountId && !host) {
      toast("请选择发件账号或填写 SMTP 主机", "error");
      return;
    }
    setIsTesting(true);
    setTestResult(null);
    try {
      const result = await api.testEmail({
        recipient,
        ...(senderAccountId
          ? { email_account_id: Number(senderAccountId), ...smtpOverride }
          : {
              ...smtpOverride,
              smtp_user: settings.email_notification_smtp_user || undefined,
              smtp_password: settings.email_notification_smtp_password || undefined,
            }),
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
          description="使用平台账号或手动 SMTP 将新邮件正文转发到指定邮箱"
          enabled={settings.email_notification_enabled === "true"}
          onChange={(value) => setSetting("email_notification_enabled", value ? "true" : "false")}
        />
        <Select
          label="发件账号"
          value={selectedSenderAccountId}
          onChange={(value) => setSetting("email_notification_account_id", value)}
          options={[{ value: "", label: "手动配置 SMTP" }, ...senderAccountOptions]}
          placeholder={senderAccountOptions.length > 0 ? "选择平台内账号" : "暂无可用账号"}
          disabled={senderAccountOptions.length === 0}
        />
        <Input
          label="转发到"
          type="email"
          value={recipient}
          onChange={(event) => setSetting("email_notification_recipient", event.target.value)}
          placeholder="archive@example.com"
          hint="也可以直接输入其他收件邮箱"
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
            hint={
              senderAccountId
                ? "内置服务商使用账号配置；自定义账号可用此处覆盖 SMTP"
                : "未选择平台内账号时使用"
            }
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
