import { AnimatePresence, motion } from "framer-motion";
import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import {
  IconActivity,
  IconAt,
  IconBell,
  IconCheck,
  IconClock,
  IconCode,
  IconCopy,
  IconDatabase,
  IconDownload,
  IconFilter,
  IconGlobe,
  IconKey,
  IconLink,
  IconMail,
  IconRefresh,
  IconServer,
  IconSettings,
  IconShield,
  IconUpload,
  IconUser,
  IconZap,
} from "../components/icons";
import { Topbar } from "../components/layout";
import { Button, Card, Input } from "../components/ui/Primitives";
import { useToast } from "../components/ui/Toast";
import { useApp } from "../store/AppContext";
import { CRON_PRESETS, maskValue } from "./impl/settings_api";

/* ───── helpers ───── */

const Toggle: React.FC<{
  enabled: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}> = ({ enabled, onChange, disabled }) => (
  <button
    type="button"
    disabled={disabled}
    onClick={() => onChange(!enabled)}
    className={`relative w-11 h-6 rounded-full transition-colors ${
      disabled ? "opacity-50 cursor-not-allowed" : ""
    } ${enabled ? "bg-gh-success" : "bg-gh-border"}`}
  >
    <motion.div
      animate={{ x: enabled ? 20 : 2 }}
      transition={{ type: "spring", stiffness: 400, damping: 30 }}
      className="absolute top-0.5 w-5 h-5 bg-white rounded-full shadow-md"
    />
  </button>
);

const SectionHeader: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <h4 className="text-xs font-semibold text-gh-text-muted uppercase tracking-wider mb-3 mt-1">
    {children}
  </h4>
);

const TestResult: React.FC<{
  result: { success: boolean; message: string } | null;
}> = ({ result }) => {
  if (!result) return null;
  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      className={`mt-2 text-xs px-3 py-1.5 rounded-md border ${
        result.success
          ? "bg-gh-success/10 border-gh-success/30 text-gh-success"
          : "bg-gh-danger/10 border-gh-danger/30 text-gh-danger"
      }`}
    >
      {result.message}
    </motion.div>
  );
};

/* ───── Tab props ───── */

interface TabProps {
  settings: Record<string, string>;
  setSetting: (key: string, value: string) => void;
  toast: (msg: string, type?: "success" | "error" | "info") => void;
  user: { is_admin: boolean } | null;
}

interface AdminUserSummary {
  id: number;
  username: string;
  is_admin: boolean;
  email_account_count: number;
  usable_email_count: number;
}

/* ═══════════════════════════════════════════
   Tab 1: 基础
   ═══════════════════════════════════════════ */

const BasicTab: React.FC<TabProps> = ({ settings, setSetting, toast, user }) => {
  const { updateCredentials } = useApp();
  const [curPwd, setCurPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [pwdLoading, setPwdLoading] = useState(false);
  const [aiTestLoading, setAiTestLoading] = useState(false);
  const [aiTestResult, setAiTestResult] = useState<{ success: boolean; message: string } | null>(
    null,
  );
  const [version, setVersion] = useState<string>("");
  const [pyVersion, setPyVersion] = useState<string>("");
  const [platform, setPlatform] = useState<string>("");
  const [hasUpdate, setHasUpdate] = useState(false);
  const [repositoryUrl, setRepositoryUrl] = useState<string>("");
  const [announcementLoading, setAnnouncementLoading] = useState(false);
  const [announcement, setAnnouncement] = useState<{
    title: string;
    body: string;
    html_url: string;
    latest_version: string;
    has_update: boolean;
  } | null>(null);
  const [showAPIKey, setShowAPIKey] = useState(false);

  useEffect(() => {
    api
      .getVersionCheck()
      .then((v) => {
        setVersion(v.current_version || v.version || "");
        setHasUpdate(v.has_update);
        setRepositoryUrl(v.repository_url || "");
      })
      .catch(() => {});
    api
      .getDeploymentInfo()
      .then((d) => {
        setPyVersion(d.python_version);
        setPlatform(d.platform);
      })
      .catch(() => {});
  }, []);

  const handlePasswordSave = async () => {
    if (!newPwd) {
      toast("请输入新密码", "error");
      return;
    }
    if (newPwd !== confirmPwd) {
      toast("两次密码不一致", "error");
      return;
    }
    setPwdLoading(true);
    try {
      await updateCredentials(user?.is_admin ? "admin" : "", newPwd);
      toast("密码已更新", "success");
      setCurPwd("");
      setNewPwd("");
      setConfirmPwd("");
    } catch (err: any) {
      toast(err.message, "error");
    } finally {
      setPwdLoading(false);
    }
  };

  const handleUpdateAnnouncement = async () => {
    setAnnouncementLoading(true);
    try {
      const res = await api.getUpdateAnnouncement();
      setAnnouncement(res);
      if (res.success) {
        toast(res.has_update ? "发现新版本公告" : "已获取最新公告", "success");
      } else {
        toast(res.title || "无法获取更新公告", "info");
      }
    } catch (err: any) {
      toast(err.message || "获取更新公告失败", "error");
    } finally {
      setAnnouncementLoading(false);
    }
  };

  const handleAITest = async () => {
    setAiTestLoading(true);
    setAiTestResult(null);
    try {
      const res = await api.testVerificationAI({
        base_url: settings.verification_ai_base_url || undefined,
        model_id: settings.verification_ai_model || undefined,
        api_key: settings.verification_ai_api_key || undefined,
      });
      setAiTestResult({
        success: res.success,
        message: res.message || (res.code ? `Code: ${res.code}` : "已测试"),
      });
    } catch (err: any) {
      setAiTestResult({ success: false, message: err.message });
    } finally {
      setAiTestLoading(false);
    }
  };

  return (
    <motion.div
      key="basic"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ type: "spring", stiffness: 300, damping: 28 }}
      className="space-y-5"
    >
      {/* Password */}
      <Card className="p-5">
        <SectionHeader>登录密码</SectionHeader>
        <div className="space-y-3 max-w-md">
          <Input
            label="当前密码"
            type="password"
            value={curPwd}
            onChange={(e) => setCurPwd(e.target.value)}
          />
          <Input
            label="新密码"
            type="password"
            value={newPwd}
            onChange={(e) => setNewPwd(e.target.value)}
          />
          {newPwd && (
            <Input
              label="确认密码"
              type="password"
              value={confirmPwd}
              onChange={(e) => setConfirmPwd(e.target.value)}
            />
          )}
          <Button variant="primary" onClick={handlePasswordSave} loading={pwdLoading}>
            更新密码
          </Button>
        </div>
      </Card>

      {/* Verification AI */}
      <Card className="p-5">
        <SectionHeader>验证码 AI</SectionHeader>
        <div className="space-y-3 max-w-lg">
          <div className="flex items-center justify-between p-3 rounded-md bg-gh-canvas-inset border border-gh-border">
            <div>
              <div className="text-sm text-gh-text">启用验证码 AI</div>
              <div className="text-xs text-gh-text-secondary">自动识别验证邮件中的验证码</div>
            </div>
            <Toggle
              enabled={settings.verification_ai_enabled === "true"}
              onChange={(v) => setSetting("verification_ai_enabled", v ? "true" : "false")}
            />
          </div>
          <Input
            label="Base URL"
            value={settings.verification_ai_base_url || ""}
            onChange={(e) => setSetting("verification_ai_base_url", e.target.value)}
            placeholder="https://api.openai.com/v1"
          />
          <Input
            label="Model ID"
            value={settings.verification_ai_model || ""}
            onChange={(e) => setSetting("verification_ai_model", e.target.value)}
            placeholder="gpt-4o-mini"
          />
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              <Input
                label="API Key"
                type={showAPIKey ? "text" : "password"}
                value={settings.verification_ai_api_key || ""}
                onChange={(e) => setSetting("verification_ai_api_key", e.target.value)}
                placeholder="sk-..."
              />
            </div>
            <Button variant="ghost" size="sm" onClick={() => setShowAPIKey(!showAPIKey)}>
              {showAPIKey ? <IconCheck size={13} /> : <IconKey size={13} />}
            </Button>
            <Button variant="secondary" size="sm" onClick={handleAITest} loading={aiTestLoading}>
              <IconZap size={13} /> 测试
            </Button>
          </div>
          <TestResult result={aiTestResult} />
        </div>
      </Card>

      {/* System Health */}
      <Card className="p-5">
        <SectionHeader>系统状态</SectionHeader>
        <div className="space-y-2 max-w-md">
          <StatusRow icon={IconActivity} label="应用版本" value={version || "..."} />
          <StatusRow icon={IconServer} label="Python" value={pyVersion || "..."} />
          <StatusRow icon={IconGlobe} label="平台" value={platform || "..."} />
          <StatusRow
            icon={IconDownload}
            label="版本更新"
            value={hasUpdate ? "有可用更新" : "已是最新"}
            color={hasUpdate ? "text-gh-warning" : "text-gh-success"}
          />
          {repositoryUrl && (
            <StatusRow
              icon={IconCode}
              label="项目仓库"
              value={repositoryUrl.replace("https://github.com/", "")}
            />
          )}
          <div className="pt-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleUpdateAnnouncement}
              loading={announcementLoading}
            >
              <IconDownload size={13} /> 获取更新公告
            </Button>
          </div>
          {announcement && (
            <div className="rounded-md border border-gh-border bg-gh-canvas-inset p-3 text-sm">
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium text-gh-text">
                  {announcement.title || announcement.latest_version}
                </div>
                <span
                  className={
                    announcement.has_update ? "text-xs text-gh-warning" : "text-xs text-gh-success"
                  }
                >
                  {announcement.has_update ? "有更新" : "当前版本"}
                </span>
              </div>
              {announcement.body && (
                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-xs text-gh-text-secondary font-sans">
                  {announcement.body}
                </pre>
              )}
              {announcement.html_url && (
                <a
                  href={announcement.html_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-flex text-xs text-gh-accent hover:underline"
                >
                  查看发布页
                </a>
              )}
            </div>
          )}
        </div>
      </Card>
    </motion.div>
  );
};

const StatusRow: React.FC<{
  icon: React.FC<{ size?: number; className?: string }>;
  label: string;
  value: string;
  color?: string;
}> = ({ icon: Icon, label, value, color = "text-gh-text" }) => (
  <div className="flex items-center justify-between px-3 py-2 rounded-md bg-gh-canvas-inset border border-gh-border">
    <span className="text-sm text-gh-text flex items-center gap-2">
      <Icon size={12} className="text-gh-text-muted" /> {label}
    </span>
    <span className={`text-xs ${color}`}>{value}</span>
  </div>
);

/* ───── prefix rules helpers ───── */

interface PrefixRules {
  min: string;
  max: string;
  regex: string;
}

const parsePrefixRules = (json: string | undefined): PrefixRules => {
  try {
    const parsed: Record<string, unknown> = JSON.parse(json || "{}");
    return {
      min: String(parsed.min_length ?? "6"),
      max: String(parsed.max_length ?? "20"),
      regex: String(parsed.regex ?? ""),
    };
  } catch {
    return { min: "6", max: "20", regex: "" };
  }
};

const serializePrefixRules = (rules: PrefixRules): string => {
  return JSON.stringify({
    min_length: parseInt(rules.min) || 6,
    max_length: parseInt(rules.max) || 20,
    regex: rules.regex || "",
  });
};

/* ═══════════════════════════════════════════
   Tab 2: 临时邮箱
   ═══════════════════════════════════════════ */

const TempMailTab: React.FC<TabProps> = ({ settings, setSetting, toast }) => {
  const [syncLoading, setSyncLoading] = useState(false);
  const [syncResult, setSyncResult] = useState<{ success: boolean; message: string } | null>(null);
  const [domains, setDomains] = useState<string[]>([]);

  /* prefix rules synced via temp_mail_prefix_rules JSON */
  const [prefixRules, setPrefixRules] = useState<PrefixRules>(() =>
    parsePrefixRules(settings.temp_mail_prefix_rules),
  );

  useEffect(() => {
    setPrefixRules(parsePrefixRules(settings.temp_mail_prefix_rules));
  }, [settings.temp_mail_prefix_rules]);

  const updatePrefixRule = (field: keyof PrefixRules, value: string) => {
    const next: PrefixRules = { ...prefixRules, [field]: value };
    setPrefixRules(next);
    setSetting("temp_mail_prefix_rules", serializePrefixRules(next));
  };

  const provider = settings.temp_mail_provider || "cloudflare_temp_mail";
  const setProvider = (v: string) => setSetting("temp_mail_provider", v);

  const handleSyncDomains = async () => {
    const workerUrl = settings.cf_worker_base_url || "";
    const adminKey = settings.cf_worker_admin_key || "";
    if (!workerUrl || !adminKey) {
      toast("请先填写 Worker URL 和 Admin Key", "error");
      return;
    }
    setSyncLoading(true);
    setSyncResult(null);
    try {
      const res = await api.syncCFDomains({ worker_url: workerUrl, admin_key: adminKey });
      setSyncResult({ success: res.success, message: res.message });
      if (res.domains?.length) setDomains(res.domains);
      toast(res.message, res.success ? "success" : "error");
    } catch (err: any) {
      setSyncResult({ success: false, message: err.message });
    } finally {
      setSyncLoading(false);
    }
  };

  return (
    <motion.div
      key="tempmail"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ type: "spring", stiffness: 300, damping: 28 }}
      className="space-y-5"
    >
      {/* Provider Selector */}
      <Card className="p-5">
        <SectionHeader>邮件提供商</SectionHeader>
        <div className="flex gap-2">
          {[
            { k: "cloudflare_temp_mail", label: "Cloudflare Temp Mail" },
            { k: "legacy_bridge", label: "Legacy Bridge (GPTMail)" },
          ].map((p) => (
            <button
              key={p.k}
              type="button"
              onClick={() => setProvider(p.k)}
              className={`px-4 py-2 text-sm font-medium rounded-md border transition-colors ${
                provider === p.k
                  ? "border-gh-accent bg-gh-accent/10 text-gh-accent"
                  : "border-gh-border text-gh-text-muted hover:text-gh-text hover:border-gh-text-muted"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </Card>

      {/* CF Worker Config */}
      {provider === "cloudflare_temp_mail" && (
        <Card className="p-5">
          <SectionHeader>Cloudflare Worker 配置</SectionHeader>
          <div className="space-y-3 max-w-lg">
            <Input
              label="Worker URL"
              value={settings.cf_worker_base_url || ""}
              onChange={(e) => setSetting("cf_worker_base_url", e.target.value)}
              placeholder="https://worker.example.workers.dev"
            />
            <Input
              label="Admin Key"
              type="password"
              value={settings.cf_worker_admin_key || ""}
              onChange={(e) => setSetting("cf_worker_admin_key", e.target.value)}
            />
            <div className="flex gap-2">
              <Button variant="secondary" onClick={handleSyncDomains} loading={syncLoading}>
                <IconRefresh size={13} /> 同步域名
              </Button>
            </div>
            <TestResult result={syncResult} />

            {domains.length > 0 && (
              <div>
                <div className="text-xs text-gh-text-muted mb-2">已同步域名 ({domains.length})</div>
                <div className="grid grid-cols-2 gap-1.5 max-h-32 overflow-y-auto">
                  {domains.map((d) => (
                    <div
                      key={d}
                      className="px-2.5 py-1 text-xs font-mono text-gh-text bg-gh-canvas-inset border border-gh-border rounded"
                    >
                      {d}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {domains.length > 0 && (
              <div>
                <label className="text-xs font-medium text-gh-text-muted">默认域名</label>
                <select
                  value={settings.temp_mail_default_domain || ""}
                  onChange={(e) => setSetting("temp_mail_default_domain", e.target.value)}
                  className="mt-1.5 w-full bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-1.5 text-sm text-gh-text focus:outline-none focus:border-gh-accent"
                >
                  <option value="">自动选择</option>
                  {domains.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="pt-2 border-t border-gh-border">
              <div className="text-xs font-semibold text-gh-text-muted mb-3">前缀规则</div>
              <div className="grid grid-cols-3 gap-3">
                <Input
                  label="最小长度"
                  type="number"
                  value={prefixRules.min}
                  onChange={(e) => updatePrefixRule("min", e.target.value)}
                />
                <Input
                  label="最大长度"
                  type="number"
                  value={prefixRules.max}
                  onChange={(e) => updatePrefixRule("max", e.target.value)}
                />
                <Input
                  label="正则"
                  value={prefixRules.regex}
                  onChange={(e) => updatePrefixRule("regex", e.target.value)}
                  placeholder="^[a-z0-9]+$"
                />
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* GPTMail Config */}
      {provider === "legacy_bridge" && (
        <Card className="p-5">
          <SectionHeader>GPTMail 配置</SectionHeader>
          <div className="space-y-3 max-w-lg">
            <Input
              label="API Base URL"
              value={settings.temp_mail_api_base_url || ""}
              onChange={(e) => setSetting("temp_mail_api_base_url", e.target.value)}
              placeholder="https://api.gptmail.example.com"
            />
            <Input
              label="API Key"
              type="password"
              value={settings.temp_mail_api_key || ""}
              onChange={(e) => setSetting("temp_mail_api_key", e.target.value)}
            />
            <div>
              <label className="text-xs font-medium text-gh-text-muted">Domains (JSON)</label>
              <textarea
                value={settings.temp_mail_domains || "[]"}
                onChange={(e) => setSetting("temp_mail_domains", e.target.value)}
                rows={4}
                className="mt-1.5 w-full bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-1.5 text-sm text-gh-text font-mono focus:outline-none focus:border-gh-accent resize-y"
                placeholder='["domain1.com", "domain2.com"]'
              />
            </div>
            <Input
              label="默认域名"
              value={settings.temp_mail_default_domain || ""}
              onChange={(e) => setSetting("temp_mail_default_domain", e.target.value)}
            />
          </div>
        </Card>
      )}
    </motion.div>
  );
};

/* ═══════════════════════════════════════════
   Tab 3: API 安全
   ═══════════════════════════════════════════ */

const ApiSecurityTab: React.FC<TabProps> = ({ settings, setSetting, toast }) => {
  const [plaintextKey, setPlaintextKey] = useState<string | null>(null);
  const [showPlaintext, setShowPlaintext] = useState(false);
  const [revealLoading, setRevealLoading] = useState(false);

  const extApiKey = settings.external_api_key || "";
  const apiKeysStr = settings.external_api_keys || "{}";

  const handleRevealPlaintext = async () => {
    setRevealLoading(true);
    try {
      const res = await api.getAPIKeyPlaintext();
      setPlaintextKey(res.external_api_key);
      setShowPlaintext(true);
    } catch (err: any) {
      toast(err.message, "error");
    } finally {
      setRevealLoading(false);
    }
  };

  const handleCopyKey = (text: string) => {
    navigator.clipboard.writeText(text);
    toast("已复制到剪贴板", "success");
  };

  return (
    <motion.div
      key="apisecurity"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ type: "spring", stiffness: 300, damping: 28 }}
      className="space-y-5"
    >
      {/* External API Key */}
      <Card className="p-5">
        <SectionHeader>外部 API Key</SectionHeader>
        <div className="space-y-3 max-w-lg">
          <div className="flex items-center gap-3">
            <div className="flex-1 px-3 py-1.5 rounded-md bg-gh-canvas-inset border border-gh-border font-mono text-sm text-gh-text">
              {showPlaintext && plaintextKey ? plaintextKey : maskValue(extApiKey, 6)}
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleCopyKey(extApiKey)}
              disabled={!extApiKey}
            >
              <IconCopy size={13} />
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={handleRevealPlaintext}
              loading={revealLoading}
            >
              <IconKey size={13} /> 查看明文
            </Button>
          </div>
          {showPlaintext && plaintextKey && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-gh-warning/10 border border-gh-warning/30 text-xs text-gh-warning"
            >
              <IconKey size={12} />
              明文 Key: {plaintextKey}
              <button
                onClick={() => handleCopyKey(plaintextKey)}
                className="ml-auto p-0.5 hover:text-gh-text"
              >
                <IconCopy size={11} />
              </button>
            </motion.div>
          )}
        </div>
      </Card>

      {/* Multiple API Keys */}
      <Card className="p-5">
        <SectionHeader>多 API Key 管理</SectionHeader>
        <div className="max-w-lg">
          <label className="text-xs font-medium text-gh-text-muted">API Keys (JSON)</label>
          <textarea
            value={apiKeysStr}
            onChange={(e) => setSetting("external_api_keys", e.target.value)}
            rows={5}
            className="mt-1.5 w-full bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-1.5 text-sm text-gh-text font-mono focus:outline-none focus:border-gh-accent resize-y"
            placeholder={'{"key1": "sk-...", "key2": "sk-..."}'}
          />
        </div>
      </Card>

      {/* Public Mode */}
      <Card className="p-5">
        <SectionHeader>公共模式</SectionHeader>
        <div className="space-y-3 max-w-lg">
          <div className="flex items-center justify-between p-3 rounded-md bg-gh-canvas-inset border border-gh-border">
            <div>
              <div className="text-sm text-gh-text">启用公共模式</div>
              <div className="text-xs text-gh-text-secondary">允许未认证请求访问公共端点</div>
            </div>
            <Toggle
              enabled={settings.external_api_public_mode === "true"}
              onChange={(v) => setSetting("external_api_public_mode", v ? "true" : "false")}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gh-text-muted">IP 白名单 (一行一个)</label>
            <textarea
              value={settings.external_api_ip_whitelist || ""}
              onChange={(e) => setSetting("external_api_ip_whitelist", e.target.value)}
              rows={3}
              className="mt-1.5 w-full bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-1.5 text-sm text-gh-text font-mono focus:outline-none focus:border-gh-accent resize-y"
              placeholder="192.168.1.0/24&#10;10.0.0.1"
            />
          </div>
        </div>
      </Card>

      {/* Rate Limit */}
      <Card className="p-5">
        <SectionHeader>速率限制</SectionHeader>
        <div className="max-w-xs">
          <Input
            label="每分钟最大请求数"
            type="number"
            value={settings.external_api_rate_limit_per_minute || "60"}
            onChange={(e) => setSetting("external_api_rate_limit_per_minute", e.target.value)}
          />
        </div>
      </Card>

      {/* Feature Toggles */}
      <Card className="p-5">
        <SectionHeader>功能开关</SectionHeader>
        <div className="space-y-2 max-w-lg">
          <ToggleRow
            label="禁用原始内容"
            desc="API 响应中不包含原始邮件内容"
            enabled={settings.external_api_disable_raw_content === "true"}
            onChange={(v) => setSetting("external_api_disable_raw_content", v ? "true" : "false")}
          />
          <ToggleRow
            label="禁用等待消息"
            desc="禁用邮件轮询等待提示"
            enabled={settings.external_api_disable_wait_message === "true"}
            onChange={(v) => setSetting("external_api_disable_wait_message", v ? "true" : "false")}
          />
        </div>
      </Card>

      {/* External Pool */}
      <Card className="p-5">
        <SectionHeader>外部邮箱池</SectionHeader>
        <div className="space-y-2 max-w-lg">
          <ToggleRow
            label="启用外部邮箱池"
            desc="允许外部服务访问邮箱池"
            enabled={settings.pool_external_enabled === "true"}
            onChange={(v) => setSetting("pool_external_enabled", v ? "true" : "false")}
          />
        </div>
      </Card>
    </motion.div>
  );
};

const ToggleRow: React.FC<{
  label: string;
  desc: string;
  enabled: boolean;
  onChange: (v: boolean) => void;
}> = ({ label, desc, enabled, onChange }) => (
  <div className="flex items-center justify-between p-3 rounded-md bg-gh-canvas-inset border border-gh-border">
    <div>
      <div className="text-sm text-gh-text">{label}</div>
      <div className="text-xs text-gh-text-secondary">{desc}</div>
    </div>
    <Toggle enabled={enabled} onChange={onChange} />
  </div>
);

/* ═══════════════════════════════════════════
   Tab 4: 自动化
   ═══════════════════════════════════════════ */

const AutomationTab: React.FC<TabProps> = ({ settings, setSetting, toast }) => {
  /* ---------- test states ---------- */
  const [cronLoading, setCronLoading] = useState(false);
  const [cronResult, setCronResult] = useState<{ valid: boolean; message: string } | null>(null);
  const [emailTestLoading, setEmailTestLoading] = useState(false);
  const [emailTestResult, setEmailTestResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const [tgTestLoading, setTgTestLoading] = useState(false);
  const [tgTestResult, setTgTestResult] = useState<{ success: boolean; message: string } | null>(
    null,
  );
  const [whTestLoading, setWhTestLoading] = useState(false);
  const [whTestResult, setWhTestResult] = useState<{ success: boolean; message: string } | null>(
    null,
  );
  const [wtLoading, setWtLoading] = useState(false);
  const [wtResult, setWtResult] = useState<{ success: boolean; message: string } | null>(null);
  const [updLoading, setUpdLoading] = useState(false);
  const [updResult, setUpdResult] = useState<{ success: boolean; message: string } | null>(null);

  const handleValidateCron = async () => {
    const cron = settings.refresh_cron || "";
    if (!cron) {
      toast("请输入 Cron 表达式", "error");
      return;
    }
    setCronLoading(true);
    setCronResult(null);
    try {
      const res = await api.validateCron(cron);
      setCronResult(res);
    } catch (err: any) {
      setCronResult({ valid: false, message: err.message });
    } finally {
      setCronLoading(false);
    }
  };

  const handleEmailTest = async () => {
    const recipient = settings.email_notification_recipient || "";
    if (!recipient) {
      toast("请填写收件邮箱", "error");
      return;
    }
    setEmailTestLoading(true);
    setEmailTestResult(null);
    try {
      const res = await api.testEmail({ recipient });
      setEmailTestResult({ success: res.success, message: res.message });
    } catch (err: any) {
      setEmailTestResult({ success: false, message: err.message });
    } finally {
      setEmailTestLoading(false);
    }
  };

  const handleTelegramTest = async () => {
    const botToken = settings.telegram_bot_token || "";
    const chatId = settings.telegram_chat_id || "";
    const proxyUrl = settings.telegram_proxy_url || undefined;
    if (!botToken || !chatId) {
      toast("请填写 Bot Token 和 Chat ID", "error");
      return;
    }
    setTgTestLoading(true);
    setTgTestResult(null);
    try {
      const res = await api.testTelegram({
        bot_token: botToken,
        chat_id: chatId,
        proxy_url: proxyUrl,
      });
      setTgTestResult({ success: res.success, message: res.message });
    } catch (err: any) {
      setTgTestResult({ success: false, message: err.message });
    } finally {
      setTgTestLoading(false);
    }
  };

  const handleWebhookTest = async () => {
    const url = settings.webhook_notification_url || "";
    const token = settings.webhook_notification_token || undefined;
    if (!url) {
      toast("请填写 Webhook URL", "error");
      return;
    }
    setWhTestLoading(true);
    setWhTestResult(null);
    try {
      const res = await api.testWebhook({ url, token });
      setWhTestResult({ success: res.success, message: res.message });
    } catch (err: any) {
      setWhTestResult({ success: false, message: err.message });
    } finally {
      setWhTestLoading(false);
    }
  };

  const handleWatchtowerTest = async () => {
    setWtLoading(true);
    setWtResult(null);
    try {
      const res = await api.testWatchtower();
      setWtResult({ success: res.success, message: res.message });
    } catch (err: any) {
      setWtResult({ success: false, message: err.message });
    } finally {
      setWtLoading(false);
    }
  };

  const handleTriggerUpdate = async () => {
    setUpdLoading(true);
    setUpdResult(null);
    try {
      const res = await api.triggerUpdate();
      setUpdResult({ success: res.success, message: res.message });
      toast(res.message, res.success ? "success" : "error");
    } catch (err: any) {
      setUpdResult({ success: false, message: err.message });
    } finally {
      setUpdLoading(false);
    }
  };

  return (
    <motion.div
      key="automation"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ type: "spring", stiffness: 300, damping: 28 }}
      className="space-y-5"
    >
      {/* Token Refresh */}
      <Card className="p-5">
        <SectionHeader>Token 刷新</SectionHeader>
        <div className="space-y-3 max-w-lg">
          <ToggleRow
            label="启用 Token 自动刷新"
            desc="定期刷新 OAuth Token 避免过期"
            enabled={settings.enable_scheduled_refresh === "true"}
            onChange={(v) => setSetting("enable_scheduled_refresh", v ? "true" : "false")}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="刷新间隔 (天)"
              type="number"
              value={settings.refresh_interval_days || "7"}
              onChange={(e) => setSetting("refresh_interval_days", e.target.value)}
            />
            <Input
              label="延迟 (秒)"
              type="number"
              value={settings.refresh_delay_seconds || "0"}
              onChange={(e) => setSetting("refresh_delay_seconds", e.target.value)}
            />
          </div>
          <div>
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <Input
                  label="Cron 表达式"
                  value={settings.refresh_cron || ""}
                  onChange={(e) => setSetting("refresh_cron", e.target.value)}
                  placeholder="0 3 * * *"
                />
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleValidateCron}
                loading={cronLoading}
              >
                <IconCheck size={13} /> 验证
              </Button>
            </div>
            <div className="flex gap-1.5 mt-2 flex-wrap">
              {CRON_PRESETS.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => setSetting("refresh_cron", p.value)}
                  className={`px-2 py-0.5 text-[11px] rounded border transition-colors ${
                    settings.refresh_cron === p.value
                      ? "border-gh-accent bg-gh-accent/10 text-gh-accent"
                      : "border-gh-border text-gh-text-muted hover:text-gh-text hover:border-gh-text-muted"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            {cronResult && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className={`mt-2 text-xs px-3 py-1.5 rounded-md border ${
                  cronResult.valid
                    ? "bg-gh-success/10 border-gh-success/30 text-gh-success"
                    : "bg-gh-danger/10 border-gh-danger/30 text-gh-danger"
                }`}
              >
                {cronResult.message}
              </motion.div>
            )}
          </div>
        </div>
      </Card>

      {/* Auto Polling */}
      <Card className="p-5">
        <SectionHeader>自动轮询</SectionHeader>
        <div className="space-y-3 max-w-lg">
          <ToggleRow
            label="启用自动轮询"
            desc="定时轮询邮箱检查新邮件"
            enabled={settings.enable_auto_polling === "true"}
            onChange={(v) => setSetting("enable_auto_polling", v ? "true" : "false")}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="轮询间隔 (秒)"
              type="number"
              value={settings.polling_interval || "30"}
              onChange={(e) => setSetting("polling_interval", e.target.value)}
            />
            <Input
              label="轮询次数"
              type="number"
              value={settings.polling_count || "10"}
              onChange={(e) => setSetting("polling_count", e.target.value)}
            />
          </div>
        </div>
      </Card>

      {/* Compact Auto Poll */}
      <Card className="p-5">
        <SectionHeader>紧凑自动轮询</SectionHeader>
        <div className="space-y-3 max-w-lg">
          <ToggleRow
            label="启用紧凑轮询"
            desc="更轻量的邮箱检查模式"
            enabled={settings.enable_compact_auto_poll === "true"}
            onChange={(v) => setSetting("enable_compact_auto_poll", v ? "true" : "false")}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="轮询间隔 (秒)"
              type="number"
              value={settings.compact_poll_interval || "15"}
              onChange={(e) => setSetting("compact_poll_interval", e.target.value)}
            />
            <Input
              label="最大次数"
              type="number"
              value={settings.compact_poll_max_count || "20"}
              onChange={(e) => setSetting("compact_poll_max_count", e.target.value)}
            />
          </div>
        </div>
      </Card>

      {/* Email Notification */}
      <Card className="p-5">
        <SectionHeader>邮件通知</SectionHeader>
        <div className="space-y-3 max-w-lg">
          <ToggleRow
            label="启用邮件通知"
            desc="通过邮件发送系统通知"
            enabled={settings.email_notification_enabled === "true"}
            onChange={(v) => setSetting("email_notification_enabled", v ? "true" : "false")}
          />
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              <Input
                label="收件邮箱"
                type="email"
                value={settings.email_notification_recipient || ""}
                onChange={(e) => setSetting("email_notification_recipient", e.target.value)}
                placeholder="admin@example.com"
              />
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={handleEmailTest}
              loading={emailTestLoading}
            >
              <IconMail size={13} /> 测试发送
            </Button>
          </div>
          <TestResult result={emailTestResult} />
        </div>
      </Card>

      {/* Telegram Notification */}
      <Card className="p-5">
        <SectionHeader>Telegram 通知</SectionHeader>
        <div className="space-y-3 max-w-lg">
          <Input
            label="Bot Token"
            type="password"
            value={settings.telegram_bot_token || ""}
            onChange={(e) => setSetting("telegram_bot_token", e.target.value)}
            placeholder="123456:ABC-DEF1234gh..."
          />
          <Input
            label="Chat ID"
            value={settings.telegram_chat_id || ""}
            onChange={(e) => setSetting("telegram_chat_id", e.target.value)}
            placeholder="-1001234567890"
          />
          <Input
            label="轮询间隔 (秒)"
            type="number"
            value={settings.telegram_poll_interval || "5"}
            onChange={(e) => setSetting("telegram_poll_interval", e.target.value)}
          />
          <Input
            label="代理 URL (可选)"
            value={settings.telegram_proxy_url || ""}
            onChange={(e) => setSetting("telegram_proxy_url", e.target.value)}
            placeholder="http://proxy:8080"
          />
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleTelegramTest}
              loading={tgTestLoading}
            >
              <IconBell size={13} /> 测试连接
            </Button>
          </div>
          <TestResult result={tgTestResult} />
        </div>
      </Card>

      {/* Webhook Notification */}
      <Card className="p-5">
        <SectionHeader>Webhook 通知</SectionHeader>
        <div className="space-y-3 max-w-lg">
          <ToggleRow
            label="启用 Webhook"
            desc="通过 HTTP Webhook 发送通知"
            enabled={settings.webhook_notification_enabled === "true"}
            onChange={(v) => setSetting("webhook_notification_enabled", v ? "true" : "false")}
          />
          <Input
            label="Webhook URL"
            value={settings.webhook_notification_url || ""}
            onChange={(e) => setSetting("webhook_notification_url", e.target.value)}
            placeholder="https://hooks.example.com/notify"
          />
          <Input
            label="Token (可选)"
            type="password"
            value={settings.webhook_notification_token || ""}
            onChange={(e) => setSetting("webhook_notification_token", e.target.value)}
          />
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleWebhookTest}
              loading={whTestLoading}
            >
              <IconLink size={13} /> 测试发送
            </Button>
          </div>
          <TestResult result={whTestResult} />
        </div>
      </Card>

      {/* One-click Update */}
      <Card className="p-5">
        <SectionHeader>一键更新</SectionHeader>
        <div className="space-y-3 max-w-lg">
          <div>
            <label className="text-xs font-medium text-gh-text-muted">更新方式</label>
            <div className="flex gap-2 mt-1.5">
              {[
                { k: "watchtower", label: "Watchtower" },
                { k: "docker", label: "Docker Compose" },
              ].map((m) => (
                <button
                  key={m.k}
                  type="button"
                  onClick={() => setSetting("update_method", m.k)}
                  className={`px-4 py-2 text-sm font-medium rounded-md border transition-colors ${
                    (settings.update_method || "watchtower") === m.k
                      ? "border-gh-accent bg-gh-accent/10 text-gh-accent"
                      : "border-gh-border text-gh-text-muted hover:text-gh-text hover:border-gh-text-muted"
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
          <Input
            label="Watchtower URL"
            value={settings.watchtower_url || ""}
            onChange={(e) => setSetting("watchtower_url", e.target.value)}
            placeholder="http://watchtower:8080"
          />
          <Input
            label="Watchtower Token"
            type="password"
            value={settings.watchtower_token || ""}
            onChange={(e) => setSetting("watchtower_token", e.target.value)}
          />
          <div className="flex gap-2 flex-wrap">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleWatchtowerTest}
              loading={wtLoading}
            >
              <IconActivity size={13} /> 测试连接
            </Button>
            <Button variant="primary" size="sm" onClick={handleTriggerUpdate} loading={updLoading}>
              <IconDownload size={13} /> 触发更新
            </Button>
          </div>
          <TestResult result={wtResult} />
          <TestResult result={updResult} />
        </div>
      </Card>
    </motion.div>
  );
};

/* ═══════════════════════════════════════════
   Tab 5: 用户管理
   ═══════════════════════════════════════════ */

const UserManagementTab: React.FC<TabProps> = ({ toast, user }) => {
  const [users, setUsers] = useState<AdminUserSummary[]>([]);
  const [registrationEnabled, setRegistrationEnabled] = useState(false);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [savingRegistration, setSavingRegistration] = useState(false);

  const loadUsers = useCallback(async () => {
    setLoadingUsers(true);
    try {
      const [registration, userRows] = await Promise.all([
        api.getRegistrationSetting(),
        api.listAdminUsers(),
      ]);
      setRegistrationEnabled(registration.registration_enabled);
      setUsers(userRows);
    } catch (err: any) {
      toast(err.message || "加载用户管理数据失败", "error");
    } finally {
      setLoadingUsers(false);
    }
  }, [toast]);

  useEffect(() => {
    if (user?.is_admin) void loadUsers();
  }, [loadUsers, user?.is_admin]);

  const handleRegistrationChange = async (enabled: boolean) => {
    setSavingRegistration(true);
    try {
      const res = await api.updateRegistrationSetting(enabled);
      setRegistrationEnabled(res.registration_enabled);
      toast(res.registration_enabled ? "已开启系统注册" : "已关闭系统注册", "success");
    } catch (err: any) {
      toast(err.message || "更新注册开关失败", "error");
    } finally {
      setSavingRegistration(false);
    }
  };

  if (!user?.is_admin) return null;

  return (
    <motion.div
      key="users"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ type: "spring", stiffness: 300, damping: 28 }}
      className="space-y-5"
    >
      <Card className="p-5">
        <SectionHeader>系统注册</SectionHeader>
        <div className="flex items-center justify-between p-3 rounded-md bg-gh-canvas-inset border border-gh-border">
          <div>
            <div className="text-sm text-gh-text">允许新用户注册</div>
            <div className="text-xs text-gh-text-secondary">关闭后仅已有用户可以登录。</div>
          </div>
          <Toggle
            enabled={registrationEnabled}
            onChange={handleRegistrationChange}
            disabled={loadingUsers || savingRegistration}
          />
        </div>
      </Card>

      <Card className="overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gh-border">
          <div>
            <SectionHeader>注册用户</SectionHeader>
            <div className="text-xs text-gh-text-secondary -mt-2">
              查看每个用户拥有的邮箱账号数与可用邮箱数。
            </div>
          </div>
          <Button variant="secondary" size="sm" onClick={loadUsers} loading={loadingUsers}>
            <IconRefresh size={13} /> 刷新
          </Button>
        </div>

        {loadingUsers ? (
          <div className="py-10 text-center text-sm text-gh-text-secondary">
            <IconRefresh size={16} className="inline animate-spin mr-2" /> 加载中...
          </div>
        ) : users.length === 0 ? (
          <div className="py-10 text-center text-sm text-gh-text-secondary">暂无用户</div>
        ) : (
          <div>
            <div className="grid grid-cols-[80px_1fr_120px_120px_120px] gap-3 px-5 py-2.5 bg-gh-canvas-inset border-b border-gh-border text-xs font-semibold text-gh-text-muted uppercase tracking-wider">
              <div>ID</div>
              <div>用户名</div>
              <div className="text-center">角色</div>
              <div className="text-center">邮箱账号</div>
              <div className="text-center">可用邮箱</div>
            </div>
            <div className="divide-y divide-gh-border/50">
              {users.map((item) => (
                <div
                  key={item.id}
                  className="grid grid-cols-[80px_1fr_120px_120px_120px] gap-3 px-5 py-3 text-sm items-center hover:bg-gh-border/20 transition-colors"
                >
                  <div className="text-xs text-gh-text-secondary tabular-nums">#{item.id}</div>
                  <div className="min-w-0 flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full bg-gradient-to-br from-gh-purple to-gh-pink flex items-center justify-center text-xs font-semibold text-white">
                      {item.username.slice(0, 1).toUpperCase()}
                    </div>
                    <span className="text-gh-text truncate">{item.username}</span>
                  </div>
                  <div className="text-center">
                    <span
                      className={
                        item.is_admin
                          ? "inline-flex px-2 py-0.5 rounded-full text-xs text-gh-warning bg-gh-warning/10 border border-gh-warning/30"
                          : "inline-flex px-2 py-0.5 rounded-full text-xs text-gh-text-secondary bg-gh-border/20 border border-gh-border"
                      }
                    >
                      {item.is_admin ? "管理员" : "普通用户"}
                    </span>
                  </div>
                  <div className="text-center text-gh-text">{item.email_account_count}</div>
                  <div className="text-center text-gh-text">{item.usable_email_count}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
    </motion.div>
  );
};

/* ═══════════════════════════════════════════
   Main Settings Page
   ═══════════════════════════════════════════ */

export const Settings: React.FC = () => {
  const { user } = useApp();
  const { toast } = useToast();
  const [tab, setTab] = useState<string>("basic");
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .getSettings()
      .then(setSettings)
      .catch((err) => toast(err.message, "error"))
      .finally(() => setLoading(false));
  }, []);

  const setSetting = useCallback((key: string, value: string) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateSettings(settings as Record<string, unknown>);
      toast("设置已保存", "success");
    } catch (err: any) {
      toast(err.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const TAB_DEFS = [
    { k: "basic", label: "基础", icon: IconSettings },
    { k: "tempmail", label: "临时邮箱", icon: IconMail },
    { k: "apisecurity", label: "API 安全", icon: IconShield },
    { k: "automation", label: "自动化", icon: IconZap },
    ...(user?.is_admin ? [{ k: "users", label: "用户管理", icon: IconUser }] : []),
  ] as const;

  const tabProps: TabProps = { settings, setSetting, toast, user };

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
      <Topbar
        title="系统设置"
        subtitle="配置邮箱服务、通知与自动化"
        actions={
          <Button variant="primary" onClick={handleSave} loading={saving} disabled={loading}>
            <IconCheck size={14} /> 保存设置
          </Button>
        }
      />

      <div className="flex-1 overflow-auto">
        <div className="max-w-3xl mx-auto p-6">
          {/* Tab Bar */}
          <div className="flex items-center gap-1 border-b border-gh-border mb-5">
            {TAB_DEFS.map((t) => (
              <button
                key={t.k}
                type="button"
                onClick={() => setTab(t.k)}
                className={`relative px-4 py-2.5 text-sm font-medium transition-colors flex items-center gap-1.5 ${
                  tab === t.k ? "text-gh-accent" : "text-gh-text-muted hover:text-gh-text"
                }`}
              >
                <t.icon size={13} />
                {t.label}
                {tab === t.k && (
                  <motion.div
                    layoutId="settings-tab-underline"
                    className="absolute bottom-0 left-0 right-0 h-0.5 bg-gh-accent rounded-full"
                    transition={{ type: "spring", stiffness: 350, damping: 30 }}
                  />
                )}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          {loading ? (
            <div className="flex items-center justify-center py-20 text-gh-text-secondary text-sm">
              <IconRefresh size={16} className="animate-spin mr-2" /> 加载中...
            </div>
          ) : (
            <AnimatePresence mode="wait">
              {tab === "basic" && <BasicTab {...tabProps} />}
              {tab === "tempmail" && <TempMailTab {...tabProps} />}
              {tab === "apisecurity" && <ApiSecurityTab {...tabProps} />}
              {tab === "automation" && <AutomationTab {...tabProps} />}
              {tab === "users" && user?.is_admin && <UserManagementTab {...tabProps} />}
            </AnimatePresence>
          )}
        </div>
      </div>
    </div>
  );
};
