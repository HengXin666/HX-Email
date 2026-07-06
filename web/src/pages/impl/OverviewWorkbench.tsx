import React, { useEffect, useMemo, useState } from "react";
import {
  IconChevronRight,
  IconCode,
  IconDatabase,
  IconKey,
  IconLink,
  IconMail,
  IconRefresh,
} from "../../components/icons";
import { Button } from "../../components/ui/Primitives";
import type {
  ActivityStats,
  EmailAccount,
  Group,
  Overview,
  Platform,
  PoolStats,
  UsableEmail,
  VerificationStats,
} from "../../types";
import { OverviewEmailList } from "./OverviewEmailList";
import { OperationPanel, OverviewMetrics } from "./OverviewWorkbenchWidgets";

interface OverviewWorkbenchProps {
  overview: Overview | null;
  emails: UsableEmail[];
  groups: Group[];
  platforms: Platform[];
  accounts: EmailAccount[];
  verificationStats: VerificationStats | null;
  poolStats: PoolStats | null;
  activityStats: ActivityStats | null;
  statsLoading: boolean;
  onRefreshStats: () => Promise<void>;
  onNavigate: (path: string) => void;
}

interface FlowStep {
  key: string;
  title: string;
  desc: string;
  metric: string;
  path: string;
  icon: React.FC<{ size?: number; className?: string }>;
  color: string;
}

export const OverviewWorkbench: React.FC<OverviewWorkbenchProps> = ({
  overview,
  emails,
  groups,
  platforms,
  accounts,
  verificationStats,
  poolStats,
  activityStats,
  statsLoading,
  onRefreshStats,
  onNavigate,
}) => {
  const visibleEmails = useMemo(
    () => emails.filter((email) => email.kind !== "alias" && email.status !== "archived"),
    [emails],
  );
  const [selectedEmailId, setSelectedEmailId] = useState<number | null>(null);

  useEffect(() => {
    if (visibleEmails.length === 0) {
      setSelectedEmailId(null);
      return;
    }
    if (!visibleEmails.some((email) => email.id === selectedEmailId)) {
      setSelectedEmailId(visibleEmails[0].id);
    }
  }, [selectedEmailId, visibleEmails]);

  const selectedEmail = visibleEmails.find((email) => email.id === selectedEmailId) ?? null;
  const activeEmails = visibleEmails.filter((email) => email.status === "active").length;
  const tempEmails = visibleEmails.filter((email) => email.kind === "temp").length;
  const flowSteps: FlowStep[] = [
    {
      key: "usable-email",
      title: "可用邮箱",
      desc: "分组、标签、邮件与验证码",
      metric: `${activeEmails}/${visibleEmails.length}`,
      path: "/accounts",
      icon: IconMail,
      color: "#58a6ff",
    },
    {
      key: "verification",
      title: "验证码",
      desc: "读取历史、链接与最新邮件",
      metric: `${verificationStats?.today_extractions ?? 0} 今日`,
      path: "/accounts",
      icon: IconKey,
      color: "#d29922",
    },
    {
      key: "bindings",
      title: "平台绑定",
      desc: "平台注册态与邮箱映射",
      metric: `${overview?.binding_count ?? 0} 绑定`,
      path: "/platforms",
      icon: IconLink,
      color: "#3fb950",
    },
    {
      key: "pool",
      title: "邮箱池",
      desc: "可用、已领、冷却、退役",
      metric: `${poolStats?.available ?? overview?.pool_available_count ?? 0} 可用`,
      path: "/pool-admin",
      icon: IconDatabase,
      color: "#a371f7",
    },
    {
      key: "api",
      title: "API 接入",
      desc: "REST 集成与外部领取",
      metric: "42 端点",
      path: "/api",
      icon: IconCode,
      color: "#f0883e",
    },
  ];

  return (
    <div className="flex-1 min-h-0 overflow-hidden p-5 md:p-6 xl:p-8">
      <div className="h-full min-h-0 max-w-[1600px] mx-auto flex flex-col gap-6">
        <OverviewMetrics
          overview={overview}
          visibleEmailCount={visibleEmails.length}
          tempEmailCount={tempEmails}
          accountCount={accounts.length}
        />

        <div className="flex-1 min-h-0 flex flex-col lg:flex-row border border-gh-border bg-gh-canvas-subtle rounded-lg overflow-hidden">
          <aside className="lg:w-72 shrink-0 border-b lg:border-b-0 lg:border-r border-gh-border bg-gh-canvas">
            <div className="min-h-12 px-5 py-3 flex items-center justify-between border-b border-gh-border">
              <span className="text-xs font-semibold text-gh-text-muted uppercase tracking-wider">
                资源流程
              </span>
              <button
                type="button"
                onClick={() => void onRefreshStats()}
                disabled={statsLoading}
                className="p-1 rounded-md text-gh-text-muted hover:text-gh-text hover:bg-gh-border/40 transition-colors disabled:opacity-50"
                title="刷新统计"
              >
                <IconRefresh size={14} />
              </button>
            </div>
            <div className="p-3 space-y-2">
              {flowSteps.map((step) => (
                <button
                  key={step.key}
                  type="button"
                  onClick={() => onNavigate(step.path)}
                  className="w-full flex items-center gap-3 rounded-md px-3 py-3 text-left text-gh-text-muted hover:text-gh-text hover:bg-gh-border/35 transition-colors"
                >
                  <span
                    className="w-8 h-8 rounded-md flex items-center justify-center shrink-0"
                    style={{ backgroundColor: `${step.color}20`, color: step.color }}
                  >
                    <step.icon size={15} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium text-gh-text truncate">
                        {step.title}
                      </span>
                      <span className="text-[11px] text-gh-text-secondary whitespace-nowrap">
                        {step.metric}
                      </span>
                    </span>
                    <span className="block text-xs text-gh-text-secondary truncate">
                      {step.desc}
                    </span>
                  </span>
                  <IconChevronRight size={13} className="shrink-0 opacity-60" />
                </button>
              ))}
            </div>
          </aside>

          <main className="flex-1 min-w-0 min-h-[320px] flex flex-col">
            <div className="min-h-14 px-5 py-3 flex items-center justify-between gap-4 border-b border-gh-border bg-gh-canvas/70">
              <div>
                <h2 className="text-sm font-semibold text-gh-text">可用邮箱主工作区</h2>
                <p className="text-[11px] text-gh-text-secondary">
                  选中邮箱后在右侧执行验证码、平台绑定、邮箱池和 API 下一步
                </p>
              </div>
              <Button variant="secondary" size="sm" onClick={() => onNavigate("/accounts")}>
                <IconMail size={13} /> 打开邮箱工作台
              </Button>
            </div>
            <div className="flex-1 min-w-0 overflow-auto">
              <OverviewEmailList
                emails={visibleEmails}
                accounts={accounts}
                selectedEmailId={selectedEmailId}
                onSelectEmail={setSelectedEmailId}
              />
            </div>
          </main>

          <OperationPanel
            selectedEmail={selectedEmail}
            groups={groups}
            platforms={platforms}
            activityStats={activityStats}
            onNavigate={onNavigate}
          />
        </div>
      </div>
    </div>
  );
};
