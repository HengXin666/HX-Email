import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import {
  IconCheck,
  IconCode,
  IconCopy,
  IconDatabase,
  IconKey,
  IconLink,
  IconRefresh,
} from "../components/icons";
import { Topbar } from "../components/layout";
import { Button, Card, Checkbox, Input, Select } from "../components/ui/Primitives";
import { useToast } from "../components/ui/Toast";
import { useApp } from "../store/AppContext";
import type { TokenConfig, TokenExchangeResult, TokenPrepareResult } from "../types";

const SCOPE_PRESETS = {
  graph: ["offline_access", "https://graph.microsoft.com/.default"],
  imap: ["offline_access", "https://outlook.office.com/IMAP.AccessAsUser.All"],
};

const DEFAULT_CONFIG: TokenConfig = {
  client_id: "",
  redirect_uri: "",
  scope: SCOPE_PRESETS.imap.join(" "),
  tenant: "consumers",
  prompt_consent: true,
};

type TokenToolTab = "guide" | "page-token" | "api-doc";

const TAB_STORAGE_KEY = "hx_token_tool_active_tab";

const TABS: Array<{
  id: TokenToolTab;
  label: string;
  description: string;
  icon: React.FC<{ size?: number; className?: string }>;
}> = [
  { id: "guide", label: "说明", description: "使用流程与注意事项", icon: IconKey },
  {
    id: "page-token",
    label: "页面 Token",
    description: "通过页面生成和保存 token",
    icon: IconLink,
  },
  {
    id: "api-doc",
    label: "API 说明",
    description: "通过 API 换取 token 并添加账号",
    icon: IconCode,
  },
];

const defaultRedirectUri = () => `${window.location.origin}/token-tool/callback`;

const parseScopes = (value: string) =>
  value
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);

const normalizeScope = (value: string) => {
  const tokens = new Set(parseScopes(value));
  tokens.add("offline_access");
  return Array.from(tokens).join(" ");
};

function getStoredTab(): TokenToolTab {
  try {
    const stored = window.localStorage?.getItem(TAB_STORAGE_KEY) as TokenToolTab | null;
    return (TABS.some((tab) => tab.id === stored) ? stored : "guide") as TokenToolTab;
  } catch {
    return "guide";
  }
}

function storeTab(tab: TokenToolTab): void {
  try {
    window.localStorage?.setItem(TAB_STORAGE_KEY, tab);
  } catch {}
}

const CodeBlock: React.FC<{ children: string }> = ({ children }) => (
  <pre className="overflow-x-auto rounded-lg border border-gh-border bg-gh-canvas-inset px-4 py-3 text-xs leading-relaxed text-gh-text font-mono">
    <code>{children}</code>
  </pre>
);

const InfoItem: React.FC<{ n: string; title: string; children: React.ReactNode }> = ({
  n,
  title,
  children,
}) => (
  <div className="flex gap-3 rounded-lg border border-gh-border bg-gh-canvas-inset p-3">
    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gh-accent/10 text-xs font-semibold text-gh-accent border border-gh-accent/20">
      {n}
    </div>
    <div className="min-w-0">
      <div className="text-sm font-semibold text-gh-text">{title}</div>
      <div className="mt-1 text-sm leading-relaxed text-gh-text-secondary">{children}</div>
    </div>
  </div>
);

export const TokenTool: React.FC = () => {
  const { refreshAccounts, refreshEmails } = useApp();
  const { toast } = useToast();
  const [activeTab, setActiveTabState] = useState<TokenToolTab>(() => getStoredTab());
  const [config, setConfig] = useState<TokenConfig>(DEFAULT_CONFIG);
  const [prepared, setPrepared] = useState<TokenPrepareResult | null>(null);
  const [callbackUrl, setCallbackUrl] = useState("");
  const [tokens, setTokens] = useState<TokenExchangeResult | null>(null);
  const [accounts, setAccounts] = useState<Array<{ id: number; email: string; status: string }>>(
    [],
  );
  const [saveMode, setSaveMode] = useState<"update" | "create">("update");
  const [accountId, setAccountId] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [scopeEntry, setScopeEntry] = useState("");
  const [loading, setLoading] = useState<string | null>(null);

  const scopeTokens = useMemo(() => parseScopes(config.scope), [config.scope]);

  const setActiveTab = (tab: TokenToolTab) => {
    setActiveTabState(tab);
    storeTab(tab);
  };

  const copyText = async (text: string, label = "内容") => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand("copy");
      } finally {
        document.body.removeChild(textarea);
      }
    }
    toast(`${label}已复制`, "success");
  };

  useEffect(() => {
    void loadInitial();
  }, []);

  const loadInitial = async () => {
    try {
      const [remoteConfig, remoteAccounts] = await Promise.all([
        api.getTokenToolConfig(),
        api.listTokenToolAccounts(),
      ]);
      setConfig({
        ...remoteConfig,
        redirect_uri: remoteConfig.redirect_uri || defaultRedirectUri(),
        scope: normalizeScope(remoteConfig.scope || DEFAULT_CONFIG.scope),
        tenant: "consumers",
      });
      setAccounts(remoteAccounts);
    } catch (err: any) {
      toast(err.message, "error");
    }
  };

  const patchConfig = (key: keyof TokenConfig, value: string | boolean) => {
    setConfig((current) => ({ ...current, [key]: value }));
  };

  const setScopePreset = (preset: keyof typeof SCOPE_PRESETS) => {
    patchConfig("scope", SCOPE_PRESETS[preset].join(" "));
  };

  const addScope = () => {
    patchConfig("scope", normalizeScope(`${config.scope} ${scopeEntry}`));
    setScopeEntry("");
  };

  const removeScope = (scope: string) => {
    if (scope === "offline_access") return;
    patchConfig("scope", normalizeScope(scopeTokens.filter((item) => item !== scope).join(" ")));
  };

  const handleSaveConfig = async () => {
    setLoading("config");
    try {
      const saved = await api.saveTokenToolConfig(config);
      setConfig({
        ...saved,
        redirect_uri: saved.redirect_uri || defaultRedirectUri(),
        scope: normalizeScope(saved.scope || DEFAULT_CONFIG.scope),
        tenant: "consumers",
      });
      toast("配置已保存", "success");
    } catch (err: any) {
      toast(err.message, "error");
    } finally {
      setLoading(null);
    }
  };

  const handlePrepare = async () => {
    setLoading("prepare");
    try {
      const result = await api.prepareTokenTool(config);
      setPrepared(result);
      toast("授权链接已生成，请复制后打开", "success");
    } catch (err: any) {
      toast(err.message, "error");
    } finally {
      setLoading(null);
    }
  };

  const handleExchange = async () => {
    setLoading("exchange");
    try {
      const result = await api.exchangeTokenTool({ callback_url: callbackUrl });
      setTokens(result);
      toast("refresh_token 已获取", "success");
    } catch (err: any) {
      toast(err.message, "error");
    } finally {
      setLoading(null);
    }
  };

  const handleSaveToken = async () => {
    if (!tokens) return;
    setLoading("save");
    try {
      await api.saveTokenTool({
        mode: saveMode,
        account_id: saveMode === "update" ? Number(accountId) : null,
        email: saveMode === "create" ? newEmail : undefined,
        client_id: tokens.client_id,
        refresh_token: tokens.refresh_token,
      });
      await Promise.all([refreshAccounts(), refreshEmails(), loadInitial()]);
      toast(saveMode === "create" ? "Outlook 账号已创建" : "Token 已保存到账号", "success");
    } catch (err: any) {
      toast(err.message, "error");
    } finally {
      setLoading(null);
    }
  };

  const renderGuide = () => (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-5">
      <Card className="p-5">
        <h2 className="text-sm font-semibold text-gh-text flex items-center gap-2 mb-4">
          <IconKey size={14} /> 使用流程
        </h2>
        <div className="space-y-3">
          <InfoItem n="1" title="配置 OAuth 参数">
            填写 Client ID、Redirect URI、Scope。Tenant 固定为 consumers，适用于个人 Microsoft /
            Outlook 账号。
          </InfoItem>
          <InfoItem n="2" title="生成授权链接">
            点击“生成授权链接”后页面只展示链接，不再自动打开新窗口。复制链接后自行在浏览器中访问并授权。
          </InfoItem>
          <InfoItem n="3" title="粘贴回调 URL 换取 Token">
            授权完成后，把浏览器跳转到的完整 callback URL 粘贴回来，页面会通过后端 API 换取
            refresh_token。
          </InfoItem>
          <InfoItem n="4" title="保存到账号">
            可以把 refresh_token 写入已有 Outlook 账号，也可以直接新建 Outlook 账号并保存凭证。
          </InfoItem>
        </div>
      </Card>

      <Card className="p-5">
        <h2 className="text-sm font-semibold text-gh-text flex items-center gap-2 mb-4">
          <IconCheck size={14} /> 当前约束
        </h2>
        <div className="space-y-3 text-sm text-gh-text-secondary leading-relaxed">
          <p>页面不会自动跳转授权链接，避免弹窗拦截、误开窗口或丢失当前编辑状态。</p>
          <p>Tab 会写入 localStorage，下次打开 token-tool 会恢复上次停留的页签。</p>
          <p>offline_access 会强制保留，否则无法获取长期可刷新的 refresh_token。</p>
        </div>
      </Card>
    </div>
  );

  const renderPageToken = () => (
    <div className="space-y-5">
      <Card className="p-5">
        <div className="flex items-center justify-between gap-3 mb-4">
          <h2 className="text-sm font-semibold text-gh-text flex items-center gap-2">
            <IconKey size={14} /> OAuth 配置
          </h2>
          <Button variant="ghost" onClick={loadInitial}>
            <IconRefresh size={14} /> 刷新
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Input
            label="Client ID"
            value={config.client_id}
            onChange={(e) => patchConfig("client_id", e.target.value)}
          />
          <Input
            label="Redirect URI"
            value={config.redirect_uri}
            onChange={(e) => patchConfig("redirect_uri", e.target.value)}
          />
          <Input label="Tenant" value="consumers" readOnly />
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-gh-text-muted">Scope 预设</label>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" onClick={() => setScopePreset("imap")}>
                IMAP
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setScopePreset("graph")}>
                Graph 邮件
              </Button>
            </div>
          </div>
        </div>

        <div className="mt-3 rounded-lg border border-gh-border bg-gh-canvas-inset p-3">
          <div className="mb-2 flex flex-wrap gap-2">
            {scopeTokens.map((scope) => (
              <span
                key={scope}
                className="inline-flex items-center gap-1 rounded-md border border-gh-border bg-gh-canvas px-2 py-1 text-xs text-gh-text"
              >
                {scope}
                {scope === "offline_access" ? (
                  <span className="text-gh-text-secondary">锁定</span>
                ) : (
                  <button
                    type="button"
                    className="text-gh-text-secondary hover:text-gh-danger"
                    onClick={() => removeScope(scope)}
                  >
                    ×
                  </button>
                )}
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <Input
              value={scopeEntry}
              onChange={(e) => setScopeEntry(e.target.value)}
              placeholder="输入 scope，支持空格 / 逗号 / 分号分隔"
              className="flex-1"
            />
            <Button variant="secondary" onClick={addScope} disabled={!scopeEntry.trim()}>
              添加
            </Button>
          </div>
          <div className="mt-2 text-xs text-gh-text-secondary">
            默认使用参考项目的 IMAP 预设：offline_access + IMAP.AccessAsUser.All。
          </div>
        </div>

        <Checkbox
          className="mt-3"
          label="强制重新授权"
          checked={config.prompt_consent}
          onChange={(checked) => patchConfig("prompt_consent", checked)}
        />

        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="secondary" onClick={handleSaveConfig} loading={loading === "config"}>
            保存配置
          </Button>
          <Button variant="primary" onClick={handlePrepare} loading={loading === "prepare"}>
            生成授权链接
          </Button>
        </div>

        {prepared && (
          <div className="mt-4 rounded-lg border border-gh-accent/25 bg-gh-accent/5 p-3">
            <div className="flex items-center justify-between gap-2 mb-2">
              <div className="text-sm font-semibold text-gh-text flex items-center gap-2">
                <IconLink size={14} /> 授权链接
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => copyText(prepared.authorize_url, "授权链接")}
              >
                <IconCopy size={13} /> 复制链接
              </Button>
            </div>
            <input
              value={prepared.authorize_url}
              readOnly
              className="w-full rounded-md border border-gh-border bg-gh-canvas-inset px-3 py-2 text-xs text-gh-text font-mono focus:outline-none focus:border-gh-accent"
            />
            <div className="mt-2 text-xs text-gh-text-secondary">
              state: <span className="font-mono text-gh-text-muted">{prepared.state}</span>
            </div>
          </div>
        )}
      </Card>

      <Card className="p-5">
        <h2 className="text-sm font-semibold text-gh-text mb-4">回调与保存</h2>
        <textarea
          value={callbackUrl}
          onChange={(e) => setCallbackUrl(e.target.value)}
          className="w-full min-h-24 bg-gh-canvas-inset border border-gh-border rounded-lg px-3 py-2 text-sm text-gh-text font-mono focus:outline-none focus:border-gh-accent focus:ring-2 focus:ring-gh-accent/25"
          placeholder="粘贴 /token-tool/callback?code=...&state=... 的完整回调 URL"
        />
        <div className="mt-3">
          <Button variant="secondary" onClick={handleExchange} loading={loading === "exchange"}>
            换取 refresh_token
          </Button>
        </div>
        {tokens && (
          <div className="mt-5 space-y-3 rounded-lg border border-gh-border bg-gh-canvas-inset p-4">
            <div className="grid grid-cols-[1fr_auto] gap-2 items-end">
              <Input
                label="Refresh Token"
                value={tokens.refresh_token}
                readOnly
                className="font-mono"
              />
              <Button
                variant="secondary"
                onClick={() => copyText(tokens.refresh_token, "Refresh Token")}
              >
                <IconCopy size={13} /> 复制
              </Button>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-[180px_1fr_auto] gap-3 items-end">
              <Select
                label="写入方式"
                value={saveMode}
                onChange={(v) => setSaveMode(v as "update" | "create")}
                options={[
                  { value: "update", label: "更新已有账号" },
                  { value: "create", label: "新建 Outlook 账号" },
                ]}
              />
              {saveMode === "update" ? (
                <Select
                  label="Outlook 账号"
                  value={accountId}
                  onChange={setAccountId}
                  options={[
                    { value: "", label: "选择账号" },
                    ...accounts.map((account) => ({ value: account.id, label: account.email })),
                  ]}
                />
              ) : (
                <Input
                  label="邮箱地址"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                />
              )}
              <Button
                variant="primary"
                onClick={handleSaveToken}
                loading={loading === "save"}
                disabled={saveMode === "update" ? !accountId : !newEmail}
              >
                保存 refresh_token
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );

  const renderApiDoc = () => (
    <div className="space-y-5">
      <Card className="p-5">
        <h2 className="text-sm font-semibold text-gh-text flex items-center gap-2 mb-4">
          <IconDatabase size={14} /> API 调用顺序
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <InfoItem n="1" title="获取凭证授权链接">
            调用 prepare 接口，传入 OAuth 配置，返回 authorize_url 与 state。
          </InfoItem>
          <InfoItem n="2" title="换取 refresh_token">
            用户授权后，把 callback URL 传给 exchange 接口，后端解析 code/state 并换 token。
          </InfoItem>
          <InfoItem n="3" title="添加或更新账号">
            调用 save 接口，把 client_id 与 refresh_token 写入已有账号或创建新 Outlook 账号。
          </InfoItem>
        </div>
      </Card>

      <Card className="p-5 space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-gh-text mb-2">1. 获取授权链接</h3>
          <CodeBlock>{`POST /api/v1/token-tool/prepare
Content-Type: application/json
Authorization: Bearer <token>

{
  "client_id": "<azure app client id>",
  "redirect_uri": "${defaultRedirectUri()}",
  "scope": "offline_access https://outlook.office.com/IMAP.AccessAsUser.All",
  "tenant": "consumers",
  "prompt_consent": true
}`}</CodeBlock>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-gh-text mb-2">响应</h3>
          <CodeBlock>{`{
  "success": true,
  "data": {
    "authorize_url": "https://login.microsoftonline.com/...",
    "authorization_url": "https://login.microsoftonline.com/...",
    "state": "...",
    "scope": "offline_access https://outlook.office.com/IMAP.AccessAsUser.All"
  }
}`}</CodeBlock>
        </div>
      </Card>

      <Card className="p-5 space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-gh-text mb-2">2. 通过回调 URL 换取 Token</h3>
          <CodeBlock>{`POST /api/v1/token-tool/exchange
Content-Type: application/json
Authorization: Bearer <token>

{
  "callback_url": "${defaultRedirectUri()}?code=<code>&state=<state>"
}`}</CodeBlock>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-gh-text mb-2">响应</h3>
          <CodeBlock>{`{
  "success": true,
  "data": {
    "client_id": "...",
    "refresh_token": "...",
    "access_token": "...",
    "expires_in": 3600,
    "token_type": "Bearer",
    "granted_scope": "...",
    "requested_scope": "..."
  }
}`}</CodeBlock>
        </div>
      </Card>

      <Card className="p-5 space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-gh-text mb-2">3. 添加账号或写入已有账号</h3>
          <CodeBlock>{`POST /api/v1/token-tool/save
Content-Type: application/json
Authorization: Bearer <token>

// 更新已有账号
{
  "mode": "update",
  "account_id": 1,
  "client_id": "...",
  "refresh_token": "..."
}

// 新建 Outlook 账号
{
  "mode": "create",
  "email": "user@outlook.com",
  "client_id": "...",
  "refresh_token": "..."
}`}</CodeBlock>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-gh-text mb-2">响应</h3>
          <CodeBlock>{`{
  "success": true,
  "data": {
    "account_id": 1,
    "email": "user@outlook.com"
  }
}`}</CodeBlock>
        </div>
      </Card>
    </div>
  );

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
      <Topbar title="Token 工具" subtitle="Outlook refresh_token 获取与写入" />
      <div className="flex-1 overflow-auto">
        <div className="max-w-5xl mx-auto p-6 space-y-5">
          <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle p-1 flex flex-wrap gap-1">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              const active = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex-1 min-w-44 rounded-lg px-3 py-2.5 text-left transition-all ${
                    active
                      ? "bg-gh-accent/10 text-gh-accent border border-gh-accent/25 shadow-sm shadow-gh-accent/10"
                      : "text-gh-text-muted border border-transparent hover:text-gh-text hover:bg-gh-border/30"
                  }`}
                >
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <Icon size={14} />
                    {tab.label}
                  </div>
                  <div className="mt-0.5 text-xs opacity-75">{tab.description}</div>
                </button>
              );
            })}
          </div>

          {activeTab === "guide"
            ? renderGuide()
            : activeTab === "page-token"
              ? renderPageToken()
              : renderApiDoc()}
        </div>
      </div>
    </div>
  );
};
