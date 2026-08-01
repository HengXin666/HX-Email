import { motion } from "framer-motion";
import type React from "react";
import { useState } from "react";
import { api } from "../../../api/client";
import { IconCopy, IconKey, IconRefresh } from "../../../components/icons";
import { Button, Card, Input } from "../../../components/ui/Primitives";
import { maskValue } from "../../../pages/impl/settings_api";
import { copyToClipboard } from "../../../utils/clipboard";
import { SectionHeader, SettingsTabFrame, ToggleRow } from "../SettingsControls";
import type { SettingsTabProps } from "../types";

export const ApiSecuritySettingsTab: React.FC<SettingsTabProps> = ({
  settings,
  setSetting,
  toast,
}) => {
  const [plaintextKey, setPlaintextKey] = useState<string | null>(null);
  const [isPlaintextVisible, setIsPlaintextVisible] = useState(false);
  const [isRevealing, setIsRevealing] = useState(false);
  const [isRotating, setIsRotating] = useState(false);
  const externalAPIKey: string = settings.external_api_key || "";

  const handleCopyKey = async (value: string): Promise<void> => {
    const didCopy: boolean = await copyToClipboard(value);
    toast(didCopy ? "已复制到剪贴板" : "复制失败，请手动复制", didCopy ? "success" : "error");
  };

  const handleReveal = async (): Promise<void> => {
    setIsRevealing(true);
    try {
      const result = await api.getAPIKeyPlaintext();
      setPlaintextKey(result.external_api_key);
      setIsPlaintextVisible(true);
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "读取 API Key 失败", "error");
    } finally {
      setIsRevealing(false);
    }
  };

  const handleRotate = async (): Promise<void> => {
    setIsRotating(true);
    try {
      const result = await api.rotateExternalAPIKey();
      setSetting("external_api_key", result.external_api_key);
      setPlaintextKey(result.external_api_key);
      setIsPlaintextVisible(true);
      toast(externalAPIKey ? "外部 API Key 已轮换" : "外部 API Key 已生成", "success");
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "生成 API Key 失败", "error");
    } finally {
      setIsRotating(false);
    }
  };

  const visibleKey: string =
    isPlaintextVisible && plaintextKey ? plaintextKey : maskValue(externalAPIKey, 6);

  return (
    <SettingsTabFrame tabKey="apisecurity">
      <Card className="p-5">
        <SectionHeader>外部 API Key</SectionHeader>
        <div className="max-w-2xl space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="min-w-64 flex-1 overflow-hidden text-ellipsis rounded-md border border-gh-border bg-gh-canvas-inset px-3 py-1.5 font-mono text-sm text-gh-text">
              {visibleKey || "尚未生成"}
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void handleCopyKey(plaintextKey || externalAPIKey)}
              disabled={!externalAPIKey}
              aria-label="复制 API Key"
              title="复制 API Key"
            >
              <IconCopy size={13} />
            </Button>
            <Button variant="secondary" size="sm" onClick={handleReveal} loading={isRevealing}>
              <IconKey size={13} /> 查看
            </Button>
            <Button variant="secondary" size="sm" onClick={handleRotate} loading={isRotating}>
              <IconRefresh size={13} /> {externalAPIKey ? "轮换" : "生成"}
            </Button>
          </div>
          {isPlaintextVisible && plaintextKey && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="rounded-md border border-gh-warning/30 bg-gh-warning/10 px-3 py-2 font-mono text-xs text-gh-warning"
            >
              此 Key 具有邮箱池访问权限，请仅提供给受信任的调用方。
            </motion.div>
          )}
        </div>
      </Card>

      <Card className="p-5">
        <SectionHeader>额外 API Keys</SectionHeader>
        <label className="block max-w-lg text-xs font-medium text-gh-text-muted">
          JSON 字符串数组
          <textarea
            value={settings.external_api_keys || "[]"}
            onChange={(event) => setSetting("external_api_keys", event.target.value)}
            rows={4}
            className="mt-1.5 w-full resize-y rounded-md border border-gh-border bg-gh-canvas-inset px-3 py-1.5 font-mono text-sm text-gh-text focus:border-gh-accent focus:outline-none"
            placeholder={'["key-one", "key-two"]'}
          />
        </label>
      </Card>

      <Card className="p-5">
        <SectionHeader>访问限制</SectionHeader>
        <div className="max-w-lg space-y-3">
          <Input
            label="每个 API Key 每分钟最大请求数"
            type="number"
            min="0"
            value={settings.external_api_rate_limit_per_minute || "60"}
            onChange={(event) =>
              setSetting("external_api_rate_limit_per_minute", event.target.value)
            }
            hint="设为 0 表示不限制"
          />
          <ToggleRow
            label="隐藏原始邮件内容"
            description="外部 API 响应中不返回原始正文"
            enabled={settings.external_api_disable_raw_content === "true"}
            onChange={(value) =>
              setSetting("external_api_disable_raw_content", value ? "true" : "false")
            }
          />
          <ToggleRow
            label="禁用等待邮件接口"
            description="关闭外部调用方的等待新邮件能力"
            enabled={settings.external_api_disable_wait_message === "true"}
            onChange={(value) =>
              setSetting("external_api_disable_wait_message", value ? "true" : "false")
            }
          />
        </div>
      </Card>

      <Card className="p-5">
        <SectionHeader>外部邮箱池 API</SectionHeader>
        <div className="max-w-lg space-y-3">
          <ToggleRow
            label="启用外部邮箱池"
            description="允许携带 X-API-Key 的服务领取、释放和完成邮箱任务"
            enabled={settings.pool_external_enabled === "true"}
            onChange={(value) => setSetting("pool_external_enabled", value ? "true" : "false")}
          />
          <div className="grid gap-1 rounded-md border border-gh-border bg-gh-canvas-inset px-3 py-2 font-mono text-xs text-gh-text-secondary">
            <span>POST /api/external/pool/claim-random</span>
            <span>POST /api/external/pool/claim-release</span>
            <span>POST /api/external/pool/claim-complete</span>
            <span>GET /api/external/pool/stats</span>
          </div>
        </div>
      </Card>
    </SettingsTabFrame>
  );
};
