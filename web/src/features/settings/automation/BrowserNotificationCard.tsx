import type React from "react";
import { useState } from "react";
import { Card } from "../../../components/ui/Primitives";
import {
  isBrowserNotifyEnabled,
  setBrowserNotifyEnabled,
} from "../../../hooks/useBrowserNotifications";
import { SectionHeader, ToggleRow } from "../SettingsControls";
import type { Toast } from "../types";

export const BrowserNotificationCard: React.FC<{ toast: Toast }> = ({ toast }) => {
  const [isEnabled, setIsEnabled] = useState(isBrowserNotifyEnabled());

  const handleToggle = async (value: boolean): Promise<void> => {
    if (value && typeof Notification !== "undefined" && Notification.permission !== "granted") {
      const permission: NotificationPermission = await Notification.requestPermission();
      if (permission !== "granted") {
        toast("浏览器通知权限被拒绝，请在站点权限中允许通知", "error");
        return;
      }
    }
    setBrowserNotifyEnabled(value);
    setIsEnabled(value);
    toast(value ? "浏览器通知已开启" : "浏览器通知已关闭", "success");
  };

  return (
    <Card className="p-5">
      <SectionHeader>浏览器通知</SectionHeader>
      <div className="max-w-lg">
        <ToggleRow
          label="新邮件系统通知"
          description="应用打开时推送新邮件主题和验证码"
          enabled={isEnabled}
          onChange={(value) => void handleToggle(value)}
        />
      </div>
    </Card>
  );
};
