import React, { useState } from "react";
import { api } from "../../api/client";
import { IconCode, IconZap } from "../../components/icons";
import { Button, Card, Checkbox, Input } from "../../components/ui/Primitives";

interface ScriptPipelineCardProps {
  settings: Record<string, string>;
  setSetting: (key: string, value: string) => void;
  isAdmin: boolean;
}

interface TestResult {
  success: boolean;
  message: string;
}

export const ScriptPipelineCard: React.FC<ScriptPipelineCardProps> = ({
  settings,
  setSetting,
  isAdmin,
}) => {
  const [isTesting, setIsTesting] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);

  if (!isAdmin) return null;

  const handleTest = async (): Promise<void> => {
    const path: string = settings.script_notification_path || "";
    if (!path) {
      setResult({ success: false, message: "请先填写 .sh 文件路径" });
      return;
    }
    setIsTesting(true);
    setResult(null);
    try {
      const parsedTimeout: number = Number(settings.script_notification_timeout || "15");
      setResult(await api.testScript(path, Number.isFinite(parsedTimeout) ? parsedTimeout : 15));
    } catch (testError: unknown) {
      setResult({
        success: false,
        message: testError instanceof Error ? testError.message : "脚本测试失败",
      });
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <Card className="p-5">
      <h4 className="flex items-center gap-2 text-xs font-semibold text-gh-text-muted uppercase tracking-wider mb-3">
        <IconCode size={13} /> Shell 流水线
      </h4>
      <div className="space-y-3 max-w-lg">
        <Checkbox
          label="新邮件触发 .sh 流水线"
          checked={settings.script_notification_enabled === "true"}
          onChange={(isEnabled: boolean) =>
            setSetting("script_notification_enabled", isEnabled ? "true" : "false")
          }
        />
        <Input
          label="脚本路径"
          value={settings.script_notification_path || ""}
          onChange={(event) => setSetting("script_notification_path", event.target.value)}
          placeholder="/data/pipelines/new-mail.sh"
        />
        <div className="grid grid-cols-1 items-end gap-2 sm:grid-cols-[1fr_auto]">
          <Input
            label="超时 (秒)"
            type="number"
            value={settings.script_notification_timeout || "15"}
            onChange={(event) => setSetting("script_notification_timeout", event.target.value)}
          />
          <Button variant="secondary" size="sm" onClick={handleTest} loading={isTesting}>
            <IconZap size={13} /> 测试执行
          </Button>
        </div>
        {result && (
          <div
            className={`text-xs px-3 py-2 rounded-md border ${
              result.success
                ? "bg-gh-success/10 border-gh-success/30 text-gh-success"
                : "bg-gh-danger/10 border-gh-danger/30 text-gh-danger"
            }`}
          >
            {result.message}
          </div>
        )}
      </div>
    </Card>
  );
};
