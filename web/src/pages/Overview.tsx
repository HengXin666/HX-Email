import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Topbar } from "../components/layout";
import { useToast } from "../components/ui/Toast";
import { useApp } from "../store/AppContext";
import type { ActivityStats, LatestMailMessage, PoolStats, VerificationStats } from "../types";
import { OverviewWorkbench } from "./impl/OverviewWorkbench";

const LATEST_MAIL_REFRESH_MS = 30_000;

export const Overview: React.FC = () => {
  const { overview, emails, groups, platforms, accounts, refreshOverview } = useApp();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [verificationStats, setVerificationStats] = useState<VerificationStats | null>(null);
  const [poolStats, setPoolStats] = useState<PoolStats | null>(null);
  const [activityStats, setActivityStats] = useState<ActivityStats | null>(null);
  const [latestMessages, setLatestMessages] = useState<LatestMailMessage[]>([]);
  const [statsLoading, setStatsLoading] = useState(false);

  useEffect(() => {
    refreshOverview();
  }, [refreshOverview]);

  const loadExtraStats = useCallback(async (): Promise<void> => {
    setStatsLoading(true);
    try {
      const [verificationResult, poolResult, activityResult, latestResult] = await Promise.all([
        api.getVerificationStats(),
        api.getPoolStats(),
        api.getActivityStats(),
        api.getLatestMessages(20),
      ]);
      setVerificationStats(verificationResult);
      setPoolStats(poolResult);
      setActivityStats(activityResult);
      setLatestMessages(latestResult);
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "加载工作台统计失败", "error");
    } finally {
      setStatsLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadExtraStats();
  }, [loadExtraStats]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void api
        .getLatestMessages(20)
        .then(setLatestMessages)
        .catch(() => undefined);
    }, LATEST_MAIL_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
      <Topbar title="邮箱工作台" subtitle="可用邮箱、验证码、平台绑定、邮箱池与 API 接入" />
      <OverviewWorkbench
        overview={overview}
        emails={emails}
        groups={groups}
        platforms={platforms}
        accounts={accounts}
        verificationStats={verificationStats}
        poolStats={poolStats}
        activityStats={activityStats}
        latestMessages={latestMessages}
        statsLoading={statsLoading}
        onRefreshStats={loadExtraStats}
        onNavigate={navigate}
      />
    </div>
  );
};
