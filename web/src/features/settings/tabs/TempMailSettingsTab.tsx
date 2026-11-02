import type React from "react";
import { useState } from "react";
import { api } from "../../../api/client";
import { IconAlertTriangle, IconRefresh, IconTrash } from "../../../components/icons";
import { Button, Card, Input, Select } from "../../../components/ui/Primitives";
import {
  isDomainExcluded,
  mergeSyncedExclusions,
  parseDomainList,
  resolveDefaultDomain,
  splitDomainsByExclusion,
  withDomainExcluded,
  withDomainRestored,
} from "../impl/temp_mail_domains";
import { SectionHeader, SettingsTabFrame, TestResult } from "../SettingsControls";
import type { SettingsTabProps, TestOutcome } from "../types";

export const TempMailSettingsTab: React.FC<SettingsTabProps> = ({
  settings,
  setSetting,
  toast,
}) => {
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<TestOutcome | null>(null);

  // 域名与排除列表都从 settings 派生: 删除/恢复只写 settings, 不另存一份 state
  const domains: string[] = parseDomainList(settings.cf_worker_domains);
  const excludedDomains: string[] = parseDomainList(settings.cf_worker_excluded_domains);
  const { available, excluded: removedDomains } = splitDomainsByExclusion(domains, excludedDomains);
  const currentDefault: string = settings.cf_worker_default_domain || "";

  /** 写回排除列表; 默认域名被删掉时立刻回退到剩余第一个可用域名。 */
  const applyExclusions = (nextExcluded: string[]): void => {
    setSetting("cf_worker_excluded_domains", JSON.stringify(nextExcluded));
    const nextDefault: string = resolveDefaultDomain(domains, nextExcluded, currentDefault);
    if (nextDefault !== currentDefault) {
      setSetting("cf_worker_default_domain", nextDefault);
    }
  };

  const handleRemoveDomain = (domain: string): void => {
    applyExclusions(withDomainExcluded(domains, excludedDomains, domain));
  };

  const handleRestoreDomain = (domain: string): void => {
    applyExclusions(withDomainRestored(domains, excludedDomains, domain));
  };

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
        const syncedDomains: string[] = result.domains;
        const syncedExcluded: string[] = mergeSyncedExclusions(
          syncedDomains,
          excludedDomains,
          result.excluded_domains,
        );
        const syncedDefault: string =
          result.default_domain && !isDomainExcluded(result.default_domain, syncedExcluded)
            ? result.default_domain
            : resolveDefaultDomain(syncedDomains, syncedExcluded, currentDefault);
        setSetting("cf_worker_domains", JSON.stringify(syncedDomains));
        setSetting("cf_worker_excluded_domains", JSON.stringify(syncedExcluded));
        if (syncedDefault !== currentDefault) {
          setSetting("cf_worker_default_domain", syncedDefault);
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
              {available.length === 0 ? (
                <div className="flex items-start gap-2 rounded-md border border-gh-warning/40 bg-gh-warning/10 px-3 py-2 text-xs text-gh-warning">
                  <IconAlertTriangle size={14} className="mt-0.5 shrink-0" />
                  <span>所有域名都已被删除，新建临时邮箱会被拒绝；请恢复至少一个域名。</span>
                </div>
              ) : (
                <div className="grid max-h-36 grid-cols-1 gap-1.5 overflow-y-auto sm:grid-cols-2">
                  {available.map((domain) => (
                    <div
                      key={domain}
                      className="flex min-w-0 items-center gap-1 rounded border border-gh-border bg-gh-canvas-inset py-0.5 pl-2.5 pr-1"
                    >
                      <span className="min-w-0 flex-1 truncate font-mono text-xs text-gh-text">
                        {domain}
                      </span>
                      <button
                        type="button"
                        aria-label={`删除域名 ${domain}`}
                        title="删除域名（不再参与轮换）"
                        onClick={() => handleRemoveDomain(domain)}
                        className="shrink-0 rounded p-1 text-gh-text-muted transition-colors hover:bg-gh-danger/10 hover:text-gh-danger"
                      >
                        <IconTrash size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              {available.length > 0 && (
                <Select
                  label="默认域名"
                  value={currentDefault || available[0] || ""}
                  onChange={(value) => setSetting("cf_worker_default_domain", value)}
                  options={available.map((domain) => ({ value: domain, label: domain }))}
                />
              )}
            </>
          )}

          {removedDomains.length > 0 && (
            <div className="space-y-1.5 border-t border-gh-border pt-3">
              <div className="text-xs font-medium text-gh-text-muted">
                已删除的域名 ({removedDomains.length})
              </div>
              {removedDomains.map((domain) => (
                <div
                  key={domain}
                  className="flex min-w-0 items-center gap-2 rounded border border-dashed border-gh-border bg-gh-canvas-inset py-1 pl-2.5 pr-1"
                >
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-gh-text-secondary line-through">
                    {domain}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`恢复域名 ${domain}`}
                    onClick={() => handleRestoreDomain(domain)}
                  >
                    <IconRefresh size={12} /> 恢复
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>
    </SettingsTabFrame>
  );
};
