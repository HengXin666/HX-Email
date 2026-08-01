import type React from "react";
import { useState } from "react";
import { api } from "../../../api/client";
import { IconRefresh } from "../../../components/icons";
import { Button, Card, Input, Select } from "../../../components/ui/Primitives";
import { SectionHeader, SettingsTabFrame, TestResult } from "../SettingsControls";
import type { SettingsTabProps, TestOutcome } from "../types";

function parseDomainList(value: string | undefined): string[] {
  try {
    const parsed: unknown = JSON.parse(value || "[]");
    return Array.isArray(parsed)
      ? parsed.filter((domain): domain is string => typeof domain === "string" && domain.length > 0)
      : [];
  } catch {
    return [];
  }
}

export const TempMailSettingsTab: React.FC<SettingsTabProps> = ({
  settings,
  setSetting,
  toast,
}) => {
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<TestOutcome | null>(null);
  const [domains, setDomains] = useState<string[]>(() =>
    parseDomainList(settings.cf_worker_domains),
  );

  const handleSyncDomains = async (): Promise<void> => {
    const workerUrl: string = settings.cf_worker_base_url || "";
    if (!workerUrl) {
      toast("请先填写 Worker URL", "error");
      return;
    }
    setIsSyncing(true);
    setSyncResult(null);
    try {
      const result = await api.syncCFDomains({
        worker_url: workerUrl,
        custom_auth: settings.cf_worker_custom_auth || "",
      });
      const message: string = result.message || (result.success ? "域名同步成功" : "域名同步失败");
      setSyncResult({ success: result.success, message });
      if (result.success && result.domains?.length) {
        setDomains(result.domains);
        setSetting("cf_worker_domains", JSON.stringify(result.domains));
        if (result.default_domain) {
          setSetting("cf_worker_default_domain", result.default_domain);
        }
      }
      toast(message, result.success ? "success" : "error");
    } catch (error: unknown) {
      const message: string = error instanceof Error ? error.message : "域名同步失败";
      setSyncResult({ success: false, message });
      toast(message, "error");
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <SettingsTabFrame tabKey="tempmail">
      <Card className="p-5">
        <SectionHeader>Cloudflare Worker</SectionHeader>
        <div className="max-w-lg space-y-3">
          <Input
            label="Worker URL"
            type="url"
            value={settings.cf_worker_base_url || ""}
            onChange={(event) => setSetting("cf_worker_base_url", event.target.value)}
            placeholder="https://worker.example.workers.dev"
          />
          <Input
            label="Admin Key"
            type="password"
            value={settings.cf_worker_admin_key || ""}
            onChange={(event) => setSetting("cf_worker_admin_key", event.target.value)}
          />
          <Input
            label="PASSWORDS (Custom Auth，可选)"
            type="password"
            value={settings.cf_worker_custom_auth || ""}
            onChange={(event) => setSetting("cf_worker_custom_auth", event.target.value)}
          />
          <Button variant="secondary" onClick={handleSyncDomains} loading={isSyncing}>
            <IconRefresh size={13} /> 同步并测试
          </Button>
          <TestResult result={syncResult} />
        </div>
      </Card>

      <Card className="p-5">
        <SectionHeader>可用域名</SectionHeader>
        <div className="max-w-lg space-y-3">
          {domains.length === 0 ? (
            <div className="rounded-md border border-gh-border bg-gh-canvas-inset px-3 py-8 text-center text-sm text-gh-text-secondary">
              尚未从 Worker 同步域名
            </div>
          ) : (
            <>
              <div className="grid max-h-36 grid-cols-1 gap-1.5 overflow-y-auto sm:grid-cols-2">
                {domains.map((domain) => (
                  <div
                    key={domain}
                    className="truncate rounded border border-gh-border bg-gh-canvas-inset px-2.5 py-1 font-mono text-xs text-gh-text"
                  >
                    {domain}
                  </div>
                ))}
              </div>
              <Select
                label="默认域名"
                value={settings.cf_worker_default_domain || domains[0] || ""}
                onChange={(value) => setSetting("cf_worker_default_domain", value)}
                options={domains.map((domain) => ({ value: domain, label: domain }))}
              />
            </>
          )}
        </div>
      </Card>
    </SettingsTabFrame>
  );
};
