import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Bell,
  Boxes,
  KeyRound,
  Mail,
  Plug,
  RefreshCw,
  Settings,
  ShieldCheck,
  Tags,
} from "lucide-react";

import { deactivateUsableEmail, loadEmailAccounts, loadMailPool, loadPlatforms, readVerification } from "../api";
import type { EmailAccount, MailPoolEntry, Platform, Session, UsableEmail } from "../types";
import { Button } from "./ui/button";
import { EmailTable, InfoPanel, Toolbar } from "./workbenchPanels";

type WorkbenchProps = {
  notice?: string;
  session: Session;
};

type TabKey =
  | "dashboard"
  | "mailboxes"
  | "verification"
  | "pool"
  | "platforms"
  | "settings"
  | "plugins"
  | "extension";

const tabs: { key: TabKey; label: string; icon: typeof Activity }[] = [
  { key: "dashboard", label: "数据概览", icon: Activity },
  { key: "mailboxes", label: "账号管理", icon: Mail },
  { key: "verification", label: "验证码提取", icon: KeyRound },
  { key: "pool", label: "号池管理", icon: Boxes },
  { key: "platforms", label: "平台绑定", icon: Tags },
  { key: "settings", label: "系统设置", icon: Settings },
  { key: "plugins", label: "插件管理", icon: Plug },
  { key: "extension", label: "浏览器扩展", icon: ShieldCheck },
];

const kindLabels: Record<UsableEmail["kind"], string> = {
  alias: "别名邮箱地址",
  custom: "可用邮箱",
  primary: "主邮箱地址",
  temp: "临时邮箱地址",
};

const statusLabels: Record<UsableEmail["status"], string> = {
  active: "可用",
  archived: "已归档",
  inactive: "已停用",
};

export function Workbench({ notice, session }: WorkbenchProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("dashboard");
  const [accounts, setAccounts] = useState<EmailAccount[]>([]);
  const [poolEntries, setPoolEntries] = useState<MailPoolEntry[]>([]);
  const [platforms, setPlatforms] = useState<Platform[]>([]);
  const [emails, setEmails] = useState<UsableEmail[]>(session.usableEmails);
  const [query, setQuery] = useState("");
  const [statusText, setStatusText] = useState(notice ?? "");

  useEffect(() => {
    setEmails(session.usableEmails);
  }, [session.usableEmails]);

  useEffect(() => {
    void Promise.all([
      loadEmailAccounts(session.accessToken),
      loadMailPool(session.accessToken),
      loadPlatforms(session.accessToken),
    ]).then(([nextAccounts, nextPool, nextPlatforms]) => {
      setAccounts(nextAccounts);
      setPoolEntries(nextPool);
      setPlatforms(nextPlatforms);
    });
  }, [session.accessToken]);

  const filteredEmails = useMemo(
    () =>
      emails.filter((email) =>
        `${email.address} ${email.label}`.toLowerCase().includes(query.toLowerCase()),
      ),
    [emails, query],
  );

  async function handleDeactivate(email: UsableEmail): Promise<void> {
    if (!session.accessToken) {
      return;
    }
    const updated = await deactivateUsableEmail(session.accessToken, email.id);
    setEmails((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    setStatusText(`${email.address} 已停用`);
  }

  async function handleVerification(email: UsableEmail): Promise<void> {
    if (!session.accessToken) {
      return;
    }
    const reading = await readVerification(session.accessToken, email.id);
    const match = reading.matches[0];
    setStatusText(match?.code ?? match?.link ?? `${email.address} 暂无验证码`);
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <Mail size={22} />
          <span>HX Email</span>
        </div>
        <nav>
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                className={activeTab === tab.key ? "nav-item active" : "nav-item"}
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                type="button"
              >
                <Icon size={17} />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </aside>
      <section className="workspace">
        <header className="topbar">
          <div>
            <p>{session.username}</p>
            <h1>Outlook Email Plus 工作台</h1>
          </div>
          <div className="topbar-actions">
            <Button type="button">
              <RefreshCw size={16} />
              刷新
            </Button>
            <Button type="button">
              <Bell size={16} />
              通知测试
            </Button>
          </div>
        </header>
        {statusText ? <p className="notice" role="status">{statusText}</p> : null}
        <div className="tab-panel animate-fade" key={activeTab}>
          {activeTab === "dashboard" ? <Dashboard session={session} /> : null}
          {activeTab === "mailboxes" ? (
            <Mailboxes
              accounts={accounts}
              emails={filteredEmails}
              onDeactivate={(email) => void handleDeactivate(email)}
              onQuery={setQuery}
              query={query}
            />
          ) : null}
          {activeTab === "verification" ? (
            <Verification emails={filteredEmails} onRead={(email) => void handleVerification(email)} />
          ) : null}
          {activeTab === "pool" ? <Pool entries={poolEntries} emails={emails} /> : null}
          {activeTab === "platforms" ? <Platforms emails={emails} platforms={platforms} /> : null}
          {activeTab === "settings" ? <SettingsPanel /> : null}
          {activeTab === "plugins" ? <PluginPanel /> : null}
          {activeTab === "extension" ? <ExtensionPanel /> : null}
        </div>
      </section>
    </main>
  );
}

function Dashboard({ session }: { session: Session }) {
  const overview = session.overview;
  const metrics = [
    ["可用邮箱", overview?.usable_email_count ?? session.usableEmails.length],
    ["活跃邮箱", overview?.active_email_count ?? 0],
    ["邮箱账号", overview?.account_count ?? 0],
    ["临时邮箱", overview?.temp_email_count ?? 0],
    ["平台绑定", overview?.binding_count ?? 0],
    ["验证码记录", overview?.verification_count ?? 0],
  ];
  return (
    <>
      <div className="metric-grid">
        {metrics.map(([label, value]) => (
          <article className="metric-card" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </div>
      <section className="split-grid">
        <InfoPanel title="刷新日志" rows={["令牌刷新状态", "失败候选重试", "批量标记失效"]} />
        <InfoPanel title="系统活动" rows={["导入导出", "邮箱池领取", "验证码读取"]} />
      </section>
    </>
  );
}

function Mailboxes({
  accounts,
  emails,
  onDeactivate,
  onQuery,
  query,
}: {
  accounts: EmailAccount[];
  emails: UsableEmail[];
  onDeactivate: (email: UsableEmail) => void;
  onQuery: (query: string) => void;
  query: string;
}) {
  return (
    <>
      <Toolbar query={query} onQuery={onQuery} />
      <section className="split-grid">
        <InfoPanel title="邮箱账号" rows={accounts.map((account) => account.primary_address)} />
        <EmailTable
          emails={emails}
          kindLabels={kindLabels}
          onDeactivate={onDeactivate}
          statusLabels={statusLabels}
        />
      </section>
    </>
  );
}

function Verification({ emails, onRead }: { emails: UsableEmail[]; onRead: (email: UsableEmail) => void }) {
  return (
    <section className="card-list">
      {emails.map((email) => (
        <article className="action-card" key={email.id}>
          <div>
            <h3>{email.address}</h3>
            <p>{kindLabels[email.kind]} · {statusLabels[email.status]}</p>
          </div>
          <Button disabled={email.status !== "active"} onClick={() => onRead(email)} type="button">
            <KeyRound size={16} />
            提取验证码
          </Button>
        </article>
      ))}
    </section>
  );
}

function Pool({ entries, emails }: { entries: MailPoolEntry[]; emails: UsableEmail[] }) {
  const rows = entries.length ? entries.map((entry) => `${entry.usable_email.address} · ${entry.status}`) : emails.map((email) => `${email.address} · 可加入号池`);
  return <InfoPanel title="邮箱池" rows={rows} />;
}

function Platforms({ emails, platforms }: { emails: UsableEmail[]; platforms: Platform[] }) {
  return (
    <section className="split-grid">
      <InfoPanel title="平台" rows={platforms.map((platform) => platform.name)} />
      <InfoPanel title="绑定候选" rows={emails.map((email) => `${email.address} · ${email.platformBindingCount ?? 0} 个平台`)} />
    </section>
  );
}

function SettingsPanel() {
  return <InfoPanel title="系统设置" rows={["修改登录密码", "注册开关", "API Key", "Telegram / Email / Webhook 通知", "自动刷新与更新检测"]} actions />;
}

function PluginPanel() {
  return <InfoPanel title="临时邮箱 Provider 插件" rows={["注册表安装", "自定义 URL 安装", "配置 Schema", "连接测试", "重新加载 Provider"]} actions />;
}

function ExtensionPanel() {
  return <InfoPanel title="浏览器扩展" rows={["领取邮箱", "等待验证码", "完成或释放任务", "生成本地注册资料"]} actions />;
}
