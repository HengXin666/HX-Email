import React from "react";
import {
  IconActivity,
  IconClock,
  IconCode,
  IconDatabase,
  IconKey,
  IconLink,
  IconMail,
  IconServer,
  IconShield,
} from "../../components/icons";
import { Badge, Button } from "../../components/ui/Primitives";
import type { ActivityStats, Group, Overview, Platform, UsableEmail } from "../../types";

type WorkbenchIcon = React.FC<{
  size?: number;
  className?: string;
  style?: React.CSSProperties;
}>;

interface MetricTileProps {
  label: string;
  value: number | string;
  icon: WorkbenchIcon;
  color: string;
}

interface OverviewMetricsProps {
  overview: Overview | null;
  visibleEmailCount: number;
  tempEmailCount: number;
  accountCount: number;
}

function getEmailKindLabel(kind: UsableEmail["kind"]): string {
  if (kind === "primary") return "主邮箱";
  if (kind === "alias") return "别名";
  if (kind === "temp") return "临时";
  return "自定义";
}

export const OverviewMetrics: React.FC<OverviewMetricsProps> = ({
  overview,
  visibleEmailCount,
  tempEmailCount,
  accountCount,
}) => (
  <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-4">
    <MetricTile
      label="可用邮箱"
      value={overview?.usable_email_count ?? visibleEmailCount}
      icon={IconMail}
      color="#58a6ff"
    />
    <MetricTile
      label="平台绑定"
      value={overview?.binding_count ?? 0}
      icon={IconLink}
      color="#3fb950"
    />
    <MetricTile
      label="邮箱池可用"
      value={overview?.pool_available_count ?? 0}
      icon={IconDatabase}
      color="#a371f7"
    />
    <MetricTile
      label="验证码记录"
      value={overview?.verification_count ?? 0}
      icon={IconKey}
      color="#d29922"
    />
    <MetricTile
      label="临时邮箱"
      value={overview?.temp_email_count ?? tempEmailCount}
      icon={IconClock}
      color="#f0883e"
    />
    <MetricTile
      label="活跃源"
      value={overview?.account_count ?? accountCount}
      icon={IconShield}
      color="#db61a2"
    />
  </div>
);

const MetricTile: React.FC<MetricTileProps> = ({ label, value, icon: Icon, color }) => (
  <div className="rounded-lg border border-gh-border bg-gh-canvas-subtle px-4 py-4">
    <div className="flex items-center justify-between gap-3">
      <span className="text-xs text-gh-text-muted">{label}</span>
      <Icon size={14} className="shrink-0" style={{ color }} />
    </div>
    <div className="mt-1 text-xl font-semibold text-gh-text tabular-nums">{value}</div>
  </div>
);

interface OperationPanelProps {
  selectedEmail: UsableEmail | null;
  groups: Group[];
  platforms: Platform[];
  activityStats: ActivityStats | null;
  onNavigate: (path: string) => void;
}

export const OperationPanel: React.FC<OperationPanelProps> = ({
  selectedEmail,
  groups,
  platforms,
  activityStats,
  onNavigate,
}) => (
  <aside className="lg:w-80 shrink-0 border-t lg:border-t-0 lg:border-l border-gh-border bg-gh-canvas flex flex-col min-h-[320px]">
    <div className="min-h-12 px-5 py-3 flex items-center border-b border-gh-border">
      <span className="text-xs font-semibold text-gh-text-muted uppercase tracking-wider">
        详情与操作
      </span>
    </div>
    <div className="flex-1 overflow-auto p-5 space-y-5">
      {selectedEmail ? (
        <>
          <div>
            <div className="flex items-center gap-2 mb-2">
              <IconMail size={15} className="text-gh-accent" />
              <h3 className="text-sm font-semibold text-gh-text truncate">
                {selectedEmail.label || selectedEmail.address}
              </h3>
            </div>
            <div className="text-xs font-mono text-gh-text-secondary break-all">
              {selectedEmail.address}
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <Badge color={selectedEmail.status === "active" ? "#3fb950" : "#6e7681"}>
                {selectedEmail.status === "active" ? "活跃" : selectedEmail.status}
              </Badge>
              <Badge color={selectedEmail.group?.color ?? "#6e7681"}>
                {selectedEmail.group?.name ?? "未分组"}
              </Badge>
              <Badge color="#58a6ff">{getEmailKindLabel(selectedEmail.kind)}</Badge>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Button variant="secondary" size="sm" onClick={() => onNavigate("/accounts")}>
              <IconKey size={13} /> 验证码
            </Button>
            <Button variant="secondary" size="sm" onClick={() => onNavigate("/platforms")}>
              <IconLink size={13} /> 绑定平台
            </Button>
            <Button variant="secondary" size="sm" onClick={() => onNavigate("/pool-admin")}>
              <IconDatabase size={13} /> 邮箱池
            </Button>
            <Button variant="secondary" size="sm" onClick={() => onNavigate("/api")}>
              <IconCode size={13} /> API
            </Button>
          </div>
        </>
      ) : (
        <div className="py-10 text-center text-sm text-gh-text-secondary">
          选择一个可用邮箱查看操作入口
        </div>
      )}

      <div className="pt-5 border-t border-gh-border">
        <h4 className="text-xs font-semibold text-gh-text-muted uppercase tracking-wider mb-2">
          资源概况
        </h4>
        <div className="grid grid-cols-3 gap-3 text-center">
          <MiniCount icon={IconServer} label="平台" value={platforms.length} />
          <MiniCount icon={IconDatabase} label="分组" value={groups.length} />
          <MiniCount icon={IconActivity} label="今日" value={activityStats?.today_actions ?? 0} />
        </div>
      </div>
    </div>
  </aside>
);

interface MiniCountProps {
  icon: WorkbenchIcon;
  label: string;
  value: number;
}

const MiniCount: React.FC<MiniCountProps> = ({ icon: Icon, label, value }) => (
  <div className="rounded-md border border-gh-border bg-gh-canvas-inset px-2 py-2">
    <Icon size={13} className="mx-auto text-gh-text-muted" />
    <div className="mt-1 text-base font-semibold text-gh-text tabular-nums">{value}</div>
    <div className="text-[11px] text-gh-text-secondary">{label}</div>
  </div>
);
