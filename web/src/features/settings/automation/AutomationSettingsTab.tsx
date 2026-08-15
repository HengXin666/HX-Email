import type React from "react";
import { Card, Input } from "../../../components/ui/Primitives";
import { DeliveryRuntimeCard } from "../DeliveryRuntimeCard";
import { ScriptPipelineCard } from "../ScriptPipelineCard";
import { SectionHeader, SettingsTabFrame, ToggleRow } from "../SettingsControls";
import type { SettingsTabProps } from "../types";
import { BrowserNotificationCard } from "./BrowserNotificationCard";
import { EmailForwardingCard } from "./EmailForwardingCard";
import { MessageForwardingCards } from "./MessageForwardingCards";

export const AutomationSettingsTab: React.FC<SettingsTabProps> = (props) => {
  const { settings, setSetting, toast, user } = props;
  return (
    <SettingsTabFrame tabKey="automation">
      <DeliveryRuntimeCard />
      <Card className="p-5">
        <SectionHeader>自动轮询</SectionHeader>
        <div className="max-w-lg space-y-3">
          <ToggleRow
            label="定期检查新邮件"
            description="按设定间隔轮询已启用分组中的邮箱"
            enabled={settings.enable_auto_polling === "true"}
            onChange={(value) => setSetting("enable_auto_polling", value ? "true" : "false")}
          />
          <div className="max-w-xs">
            <Input
              label="轮询间隔 (秒)"
              type="number"
              min="3"
              max="86400"
              value={settings.polling_interval || "30"}
              onChange={(event) => setSetting("polling_interval", event.target.value)}
            />
          </div>
        </div>
      </Card>
      <Card className="p-5">
        <SectionHeader>新建分组默认选项</SectionHeader>
        <div className="max-w-lg space-y-3">
          <div className="max-w-xs">
            <Input
              label="默认代理地址（可选）"
              placeholder="例如: 127.0.0.1:7890 或 http://host:port"
              value={settings.group_default_proxy_url || ""}
              onChange={(event) => setSetting("group_default_proxy_url", event.target.value)}
            />
          </div>
          <ToggleRow
            label="自动轮询组内邮箱"
            description="新建分组时默认勾选「自动轮询组内邮箱」；导入分组未指定时也按此配置"
            enabled={settings.group_default_polling_enabled !== "false"}
            onChange={(value) =>
              setSetting("group_default_polling_enabled", value ? "true" : "false")
            }
          />
          <ToggleRow
            label="发送新邮件通知与转发"
            description="新建分组时默认勾选「发送新邮件通知与转发」；导入分组未指定时也按此配置"
            enabled={settings.group_default_notify_enabled !== "false"}
            onChange={(value) =>
              setSetting("group_default_notify_enabled", value ? "true" : "false")
            }
          />
        </div>
      </Card>
      <BrowserNotificationCard toast={toast} />
      <EmailForwardingCard {...props} />
      <MessageForwardingCards {...props} />
      <ScriptPipelineCard
        settings={settings}
        setSetting={setSetting}
        isAdmin={Boolean(user?.is_admin)}
      />
    </SettingsTabFrame>
  );
};
