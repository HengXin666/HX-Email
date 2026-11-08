import type React from "react";
import { useState } from "react";
import { api } from "../../../api/client";
import {
  IconAlertTriangle,
  IconChevronDown,
  IconRefresh,
  IconTrash,
} from "../../../components/icons";
import { Button, Card, Input } from "../../../components/ui/Primitives";
import {
  mergeSyncedExclusions,
  splitDomainsByExclusion,
  withDomainExcluded,
  withDomainRestored,
} from "../impl/temp_mail_domains";
import { type TempMailUpstream, upstreamLabel } from "../impl/temp_mail_upstreams";
import { SectionHeader, SettingsToggle, TestResult } from "../SettingsControls";
import type { TestOutcome, Toast } from "../types";

type UpstreamPatch = Partial<Omit<TempMailUpstream, "id">>;

interface TempMailUpstreamCardProps {
  upstream: TempMailUpstream;
  index: number;
  total: number;
  /** `preferredDefault`: 同步后 Worker 给的默认域名, 供全局默认域名失效时回退。 */
  onChange: (patch: UpstreamPatch, preferredDefault?: string) => void;
  onRemove: () => void;
  onMove: (offset: -1 | 1) => void;
  toast: Toast;
}

export const TempMailUpstreamCard: React.FC<TempMailUpstreamCardProps> = ({
  upstream,
  index,
  total,
  onChange,
  onRemove,
  onMove,
  toast,
}) => {
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<TestOutcome | null>(null);
  const label: string = upstreamLabel(upstream, index);
  const { available, excluded: removedDomains } = splitDomainsByExclusion(
    upstream.domains,
    upstream.excluded_domains,
  );
  const missingCredentials: boolean =
    upstream.enabled && (!upstream.base_url || !upstream.admin_key);

  const handleRemoveDomain = (domain: string): void => {
    onChange({
      excluded_domains: withDomainExcluded(upstream.domains, upstream.excluded_domains, domain),
    });
  };

  const handleRestoreDomain = (domain: string): void => {
    onChange({
      excluded_domains: withDomainRestored(upstream.domains, upstream.excluded_domains, domain),
    });
  };

  const handleRemoveUpstream = (): void => {
    const message = `删除上游「${label}」? 用它创建的临时邮箱将无法再收信。`;
    if (typeof window !== "undefined" && !window.confirm(message)) return;
    onRemove();
  };

  const handleSync = async (): Promise<void> => {
    if (!upstream.base_url) {
      toast("请先填写 Worker URL", "error");
      return;
    }
    setIsSyncing(true);
    setSyncResult(null);
    try {
      const result = await api.syncCFDomains({
        upstream_id: upstream.id,
        worker_url: upstream.base_url,
        custom_auth: upstream.custom_auth,
      });
      const message: string = result.message || (result.success ? "域名同步成功" : "域名同步失败");
      setSyncResult({ success: result.success, message });
      if (result.success && result.domains?.length) {
        onChange(
          {
            domains: result.domains,
            excluded_domains: mergeSyncedExclusions(
              result.domains,
              upstream.excluded_domains,
              result.excluded_domains,
            ),
          },
          result.default_domain,
        );
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
    <Card className="p-5">
      <div className="mb-3 flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <SectionHeader>{label}</SectionHeader>
        </div>
        <SettingsToggle enabled={upstream.enabled} onChange={(enabled) => onChange({ enabled })} />
        <Button
          variant="ghost"
          size="sm"
          aria-label={`上移上游 ${label}`}
          disabled={index === 0}
          onClick={() => onMove(-1)}
        >
          <IconChevronDown size={12} className="rotate-180" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-label={`下移上游 ${label}`}
          disabled={index === total - 1}
          onClick={() => onMove(1)}
        >
          <IconChevronDown size={12} />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-label={`删除上游 ${label}`}
          onClick={handleRemoveUpstream}
        >
          <IconTrash size={12} />
        </Button>
      </div>
      <div className="max-w-lg space-y-3">
        <Input
          label="名称 (可选)"
          value={upstream.name}
          onChange={(event) => onChange({ name: event.target.value })}
          placeholder="例如: 主 Worker"
        />
        <Input
          label="Worker URL"
          type="url"
          value={upstream.base_url}
          onChange={(event) => onChange({ base_url: event.target.value })}
          placeholder="https://worker.example.workers.dev"
        />
        <Input
          label="Admin Key"
          type="password"
          value={upstream.admin_key}
          onChange={(event) => onChange({ admin_key: event.target.value })}
        />
        <Input
          label="PASSWORDS (Custom Auth，可选)"
          type="password"
          value={upstream.custom_auth}
          onChange={(event) => onChange({ custom_auth: event.target.value })}
        />
        {missingCredentials && (
          <div className="flex items-start gap-2 rounded-md border border-gh-warning/40 bg-gh-warning/10 px-3 py-2 text-xs text-gh-warning">
            <IconAlertTriangle size={14} className="mt-0.5 shrink-0" />
            <span>
              已启用的上游必须填写 Worker URL 和 Admin Key，否则无法保存；暂时不用可先关闭。
            </span>
          </div>
        )}
        <Button variant="secondary" onClick={handleSync} loading={isSyncing}>
          <IconRefresh size={13} /> 同步并测试
        </Button>
        <TestResult result={syncResult} />

        {upstream.domains.length === 0 ? (
          <div className="rounded-md border border-gh-border bg-gh-canvas-inset px-3 py-6 text-center text-sm text-gh-text-secondary">
            尚未从 Worker 同步域名
          </div>
        ) : available.length === 0 ? (
          <div className="flex items-start gap-2 rounded-md border border-gh-warning/40 bg-gh-warning/10 px-3 py-2 text-xs text-gh-warning">
            <IconAlertTriangle size={14} className="mt-0.5 shrink-0" />
            <span>该上游的域名都已被删除，它不会再用于新建临时邮箱。</span>
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
  );
};
