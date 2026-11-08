import type React from "react";
import { IconAlertTriangle, IconPlus } from "../../../components/icons";
import { Button, Card, Select } from "../../../components/ui/Primitives";
import {
  createUpstream,
  moveUpstream,
  parseUpstreams,
  patchUpstream,
  removeUpstream,
  resolveGlobalDefault,
  serializeUpstreams,
  type TempMailUpstream,
  usableDomainOptions,
} from "../impl/temp_mail_upstreams";
import { SectionHeader, SettingsTabFrame } from "../SettingsControls";
import type { SettingsTabProps } from "../types";
import { TempMailUpstreamCard } from "./TempMailUpstreamCard";

/**
 * 临时邮箱设置: 多个 CF Worker 上游卡片 + 全局默认域名, 所有编辑都只写本地 settings
 * .agents/notes/implemented/feature/2026-11-08-temp-mail-multi-upstream.md
 */
export const TempMailSettingsTab: React.FC<SettingsTabProps> = ({
  settings,
  setSetting,
  toast,
}) => {
  // 上游与域名都从 settings 派生: 所有编辑只写 settings, 由「保存设置」统一 PUT
  const upstreams: TempMailUpstream[] = parseUpstreams(settings);
  const domainOptions = usableDomainOptions(upstreams);
  const hasSyncedDomains: boolean = upstreams.some((upstream) => upstream.domains.length > 0);
  const currentDefault: string = settings.cf_worker_default_domain || "";

  /** 写回上游列表; 全局默认域名失效时回退到 `preferredDefault` 或并集里的第一个。 */
  const commit = (next: TempMailUpstream[], preferredDefault = ""): void => {
    setSetting("cf_worker_upstreams", serializeUpstreams(next));
    const nextDefault: string = resolveGlobalDefault(next, currentDefault, preferredDefault);
    if (nextDefault !== currentDefault) {
      setSetting("cf_worker_default_domain", nextDefault);
    }
  };

  return (
    <SettingsTabFrame tabKey="tempmail">
      {upstreams.length === 0 && (
        <Card className="p-5">
          <div className="rounded-md border border-gh-border bg-gh-canvas-inset px-3 py-8 text-center text-sm text-gh-text-secondary">
            尚未添加 CF Worker 上游
          </div>
        </Card>
      )}

      {upstreams.map((upstream, index) => (
        <TempMailUpstreamCard
          key={upstream.id}
          upstream={upstream}
          index={index}
          total={upstreams.length}
          toast={toast}
          onChange={(patch, preferredDefault) =>
            commit(patchUpstream(upstreams, upstream.id, patch), preferredDefault)
          }
          onRemove={() => commit(removeUpstream(upstreams, upstream.id))}
          onMove={(offset) => commit(moveUpstream(upstreams, upstream.id, offset))}
        />
      ))}

      <div>
        <Button
          variant="secondary"
          onClick={() => commit([...upstreams, createUpstream(upstreams)])}
        >
          <IconPlus size={13} /> 添加上游
        </Button>
      </div>

      <Card className="p-5">
        <SectionHeader>默认域名</SectionHeader>
        <div className="max-w-lg space-y-3">
          {domainOptions.length > 0 ? (
            <Select
              label="默认域名"
              value={currentDefault || domainOptions[0]?.domain || ""}
              onChange={(value) => setSetting("cf_worker_default_domain", value)}
              options={domainOptions.map((option) => ({
                value: option.domain,
                label: `${option.domain} · ${option.upstreamLabel}`,
              }))}
            />
          ) : hasSyncedDomains ? (
            <div className="flex items-start gap-2 rounded-md border border-gh-warning/40 bg-gh-warning/10 px-3 py-2 text-xs text-gh-warning">
              <IconAlertTriangle size={14} className="mt-0.5 shrink-0" />
              <span>所有域名都已被删除，新建临时邮箱会被拒绝；请恢复至少一个域名。</span>
            </div>
          ) : (
            <div className="text-sm text-gh-text-secondary">
              同步域名后可在这里选择默认域名；新建邮箱会交给提供该域名的上游。
            </div>
          )}
        </div>
      </Card>
    </SettingsTabFrame>
  );
};
