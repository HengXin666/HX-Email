import type React from "react";
import { useState } from "react";
import { api } from "../../../api/client";
import { IconBell, IconLink } from "../../../components/icons";
import { Button, Card, Input } from "../../../components/ui/Primitives";
import { SectionHeader, TestResult, ToggleRow } from "../SettingsControls";
import type { SettingsTabProps, TestOutcome } from "../types";

export const MessageForwardingCards: React.FC<SettingsTabProps> = ({
  settings,
  setSetting,
  toast,
}) => {
  const [isTestingTelegram, setIsTestingTelegram] = useState(false);
  const [telegramResult, setTelegramResult] = useState<TestOutcome | null>(null);
  const [isTestingWebhook, setIsTestingWebhook] = useState(false);
  const [webhookResult, setWebhookResult] = useState<TestOutcome | null>(null);

  const handleTelegramTest = async (): Promise<void> => {
    const botToken: string = settings.telegram_bot_token || "";
    const chatId: string = settings.telegram_chat_id || "";
    if (!botToken || !chatId) {
      toast("请填写 Bot Token 和 Chat ID", "error");
      return;
    }
    setIsTestingTelegram(true);
    setTelegramResult(null);
    try {
      const result = await api.testTelegram({
        bot_token: botToken,
        chat_id: chatId,
        proxy_url: settings.telegram_proxy_url || undefined,
      });
      setTelegramResult({ success: result.success, message: result.message });
    } catch (error: unknown) {
      setTelegramResult({
        success: false,
        message: error instanceof Error ? error.message : "Telegram 测试失败",
      });
    } finally {
      setIsTestingTelegram(false);
    }
  };

  const handleWebhookTest = async (): Promise<void> => {
    const url: string = settings.webhook_notification_url || "";
    if (!url) {
      toast("请填写 Webhook URL", "error");
      return;
    }
    setIsTestingWebhook(true);
    setWebhookResult(null);
    try {
      const result = await api.testWebhook({
        url,
        token: settings.webhook_notification_token || undefined,
      });
      setWebhookResult({ success: result.success, message: result.message });
    } catch (error: unknown) {
      setWebhookResult({
        success: false,
        message: error instanceof Error ? error.message : "Webhook 测试失败",
      });
    } finally {
      setIsTestingWebhook(false);
    }
  };

  return (
    <>
      <Card className="p-5">
        <SectionHeader>Telegram 提醒</SectionHeader>
        <div className="max-w-lg space-y-3">
          <ToggleRow
            label="启用 Telegram"
            description="新邮件到达时发送邮箱、主题和验证码"
            enabled={settings.telegram_notification_enabled === "true"}
            onChange={(value) =>
              setSetting("telegram_notification_enabled", value ? "true" : "false")
            }
          />
          <Input
            label="Bot Token"
            type="password"
            value={settings.telegram_bot_token || ""}
            onChange={(event) => setSetting("telegram_bot_token", event.target.value)}
          />
          <Input
            label="Chat ID"
            value={settings.telegram_chat_id || ""}
            onChange={(event) => setSetting("telegram_chat_id", event.target.value)}
          />
          <Input
            label="代理 URL (可选)"
            value={settings.telegram_proxy_url || ""}
            onChange={(event) => setSetting("telegram_proxy_url", event.target.value)}
            placeholder="http://proxy:8080"
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={handleTelegramTest}
            loading={isTestingTelegram}
          >
            <IconBell size={13} /> 测试发送
          </Button>
          <TestResult result={telegramResult} />
        </div>
      </Card>

      <Card className="p-5">
        <SectionHeader>Webhook 回调</SectionHeader>
        <div className="max-w-lg space-y-3">
          <ToggleRow
            label="启用 Webhook"
            description="新邮件到达时向回调地址发送结构化 JSON"
            enabled={settings.webhook_notification_enabled === "true"}
            onChange={(value) =>
              setSetting("webhook_notification_enabled", value ? "true" : "false")
            }
          />
          <Input
            label="Webhook URL"
            type="url"
            value={settings.webhook_notification_url || ""}
            onChange={(event) => setSetting("webhook_notification_url", event.target.value)}
            placeholder="https://hooks.example.com/new-mail"
          />
          <Input
            label="Bearer Token (可选)"
            type="password"
            value={settings.webhook_notification_token || ""}
            onChange={(event) => setSetting("webhook_notification_token", event.target.value)}
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={handleWebhookTest}
            loading={isTestingWebhook}
          >
            <IconLink size={13} /> 测试发送
          </Button>
          <TestResult result={webhookResult} />
        </div>
      </Card>
    </>
  );
};
