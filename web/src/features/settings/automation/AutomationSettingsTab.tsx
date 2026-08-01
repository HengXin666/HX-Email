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
