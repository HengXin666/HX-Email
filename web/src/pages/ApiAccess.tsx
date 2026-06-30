import { motion } from "framer-motion";
import React, { useState } from "react";
import {
  IconCheck,
  IconCode,
  IconCopy,
  IconDatabase,
  IconGlobe,
  IconKey,
  IconShield,
} from "../components/icons";
import { Topbar } from "../components/layout";
import { Button, Card } from "../components/ui/Primitives";
import { useToast } from "../components/ui/Toast";

interface EndpointRowProps {
  method: string;
  path: string;
  desc: string;
}

const methodColor: Record<string, string> = {
  GET: "text-gh-success bg-gh-success/10 border-gh-success/30",
  POST: "text-gh-accent bg-gh-accent/10 border-gh-accent/30",
  PUT: "text-gh-warning bg-gh-warning/10 border-gh-warning/30",
  DELETE: "text-gh-danger bg-gh-danger/10 border-gh-danger/30",
};

const EndpointRow: React.FC<EndpointRowProps> = ({ method, path, desc }) => (
  <div className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-gh-border/30 transition-colors group">
    <span
      className={`text-[10px] font-bold px-1.5 py-0.5 rounded border font-mono ${methodColor[method]}`}
    >
      {method}
    </span>
    <code className="text-xs text-gh-text font-mono flex-1 truncate">{path}</code>
    <span className="text-xs text-gh-text-secondary hidden md:block flex-1 truncate">{desc}</span>
  </div>
);

const CodeBlock: React.FC<{ code: string; language?: string }> = ({ code, language = "bash" }) => {
  const { toast } = useToast();
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative rounded-lg border border-gh-border bg-gh-canvas-inset overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 bg-gh-border/30 border-b border-gh-border">
        <span className="text-[10px] text-gh-text-secondary uppercase">{language}</span>
        <button
          onClick={() => {
            navigator.clipboard.writeText(code);
            toast("已复制", "success");
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
          className="text-gh-text-muted hover:text-gh-text transition-colors p-1"
        >
          {copied ? <IconCheck size={12} className="text-gh-success" /> : <IconCopy size={12} />}
        </button>
      </div>
      <pre className="p-3 text-xs font-mono text-gh-text overflow-x-auto leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  );
};

export const ApiAccess: React.FC = () => {
  const [tab, setTab] = useState<"overview" | "endpoints" | "examples">("overview");
  const token = localStorage.getItem("hx_token") || "<your_token>";
  const baseUrl = window.location.origin + "/api/v1";

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
      <Topbar title="API 接入" subtitle="通过 REST API 集成 HX-Email 服务" />

      <div className="flex-1 overflow-auto">
        <div className="max-w-5xl mx-auto p-6 space-y-5">
          {/* Hero */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-xl border border-gh-border bg-gradient-to-br from-gh-canvas-subtle via-gh-canvas to-gh-accent/5 p-6 overflow-hidden relative"
          >
            <div className="absolute top-0 right-0 w-64 h-64 bg-gh-accent/10 rounded-full blur-3xl" />
            <div className="relative flex items-start gap-4">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-gh-accent to-gh-purple flex items-center justify-center shadow-lg shadow-gh-accent/30">
                <IconCode size={22} className="text-white" />
              </div>
              <div className="flex-1">
                <h2 className="text-xl font-bold text-gh-text">HX-Email REST API</h2>
                <p className="text-sm text-gh-text-muted mt-1 max-w-2xl">
                  基于 FastAPI 构建，共 42
                  个端点，支持邮箱管理、平台绑定、临时邮箱、验证码读取等核心能力。
                </p>
                <div className="flex flex-wrap gap-3 mt-4">
                  <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-gh-canvas-inset border border-gh-border text-xs">
                    <IconGlobe size={12} className="text-gh-accent" />
                    <span className="text-gh-text-secondary">Base URL</span>
                    <code className="text-gh-text font-mono">{baseUrl}</code>
                  </div>
                  <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-gh-canvas-inset border border-gh-border text-xs">
                    <IconShield size={12} className="text-gh-success" />
                    <span className="text-gh-text-secondary">Bearer Token</span>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>

          {/* Tabs */}
          <div className="flex items-center gap-1 border-b border-gh-border">
            {[
              { k: "overview", label: "快速入门" },
              { k: "endpoints", label: "接口列表" },
              { k: "examples", label: "代码示例" },
            ].map((t) => (
              <button
                key={t.k}
                onClick={() => setTab(t.k as any)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  tab === t.k
                    ? "border-gh-accent text-gh-accent"
                    : "border-transparent text-gh-text-muted hover:text-gh-text"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {tab === "overview" && (
            <div className="space-y-4">
              <div className="grid md:grid-cols-3 gap-3">
                {[
                  {
                    icon: IconKey,
                    color: "#58a6ff",
                    title: "Bearer Token",
                    desc: "所有需要认证的接口通过 Header 传递 Authorization",
                  },
                  {
                    icon: IconDatabase,
                    color: "#3fb950",
                    title: "JSON 格式",
                    desc: "请求/响应统一使用 JSON 格式，Content-Type: application/json",
                  },
                  {
                    icon: IconShield,
                    color: "#a371f7",
                    title: "用户隔离",
                    desc: "每个用户的数据相互隔离，Token 对应具体用户",
                  },
                ].map((item, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.05 }}
                  >
                    <Card className="p-4">
                      <item.icon size={20} style={{ color: item.color }} />
                      <div className="mt-2 font-semibold text-gh-text">{item.title}</div>
                      <div className="text-xs text-gh-text-secondary mt-1">{item.desc}</div>
                    </Card>
                  </motion.div>
                ))}
              </div>

              <div>
                <h3 className="text-sm font-semibold text-gh-text mb-2">认证方式</h3>
                <CodeBlock language="http" code={`Authorization: Bearer ${token}`} />
              </div>

              <div>
                <h3 className="text-sm font-semibold text-gh-text mb-2">登录获取 Token</h3>
                <CodeBlock
                  language="bash"
                  code={`curl -X POST ${baseUrl}/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"username":"demo","password":"demo"}'`}
                />
              </div>

              <div>
                <h3 className="text-sm font-semibold text-gh-text mb-2">响应格式</h3>
                <CodeBlock
                  language="json"
                  code={`{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": 1,
    "username": "demo",
    "is_admin": false
  }
}`}
                />
              </div>
            </div>
          )}

          {tab === "endpoints" && (
            <div className="rounded-xl border border-gh-border bg-gh-canvas-subtle overflow-hidden">
              <div className="px-4 py-2 border-b border-gh-border bg-gh-canvas-inset">
                <span className="text-xs font-semibold text-gh-text-muted uppercase tracking-wider">
                  42 个接口
                </span>
              </div>
              <div className="p-2">
                <div className="text-[11px] font-semibold text-gh-accent uppercase tracking-wider px-3 py-1.5">
                  系统 & 认证
                </div>
                <EndpointRow method="GET" path="/health" desc="健康检查" />
                <EndpointRow method="POST" path="/auth/login" desc="登录" />
                <EndpointRow method="POST" path="/auth/register" desc="注册" />
                <EndpointRow method="POST" path="/auth/logout" desc="注销" />

                <div className="text-[11px] font-semibold text-gh-accent uppercase tracking-wider px-3 py-1.5 mt-3">
                  工作台
                </div>
                <EndpointRow method="GET" path="/workbench/overview" desc="工作台概览统计" />
                <EndpointRow method="GET" path="/workbench/usable-emails" desc="分页查询可用邮箱" />
                <EndpointRow method="POST" path="/groups" desc="创建分组" />
                <EndpointRow method="POST" path="/tags" desc="创建标签" />

                <div className="text-[11px] font-semibold text-gh-accent uppercase tracking-wider px-3 py-1.5 mt-3">
                  可用邮箱
                </div>
                <EndpointRow method="POST" path="/usable-emails" desc="创建自定义邮箱" />
                <EndpointRow method="GET" path="/usable-emails" desc="所有可用邮箱" />
                <EndpointRow
                  method="PUT"
                  path="/usable-emails/:id/organize"
                  desc="整理邮箱 (标签/分组)"
                />
                <EndpointRow
                  method="POST"
                  path="/usable-emails/:id/verification/read"
                  desc="读取验证码"
                />
                <EndpointRow
                  method="GET"
                  path="/usable-emails/:id/verification/history"
                  desc="验证历史"
                />

                <div className="text-[11px] font-semibold text-gh-accent uppercase tracking-wider px-3 py-1.5 mt-3">
                  平台
                </div>
                <EndpointRow method="POST" path="/platforms" desc="创建平台" />
                <EndpointRow method="GET" path="/platforms" desc="平台列表" />
                <EndpointRow method="PUT" path="/platforms/:id" desc="更新平台" />
                <EndpointRow
                  method="POST"
                  path="/usable-emails/:id/platform-bindings"
                  desc="绑定平台"
                />

                <div className="text-[11px] font-semibold text-gh-accent uppercase tracking-wider px-3 py-1.5 mt-3">
                  邮箱池
                </div>
                <EndpointRow method="POST" path="/mail-pool/entries" desc="加入邮箱池" />
                <EndpointRow method="GET" path="/mail-pool/entries" desc="邮箱池列表" />
                <EndpointRow method="POST" path="/mail-pool/claim" desc="领取邮箱" />
                <EndpointRow method="POST" path="/mail-pool/entries/:id/release" desc="释放邮箱" />

                <div className="text-[11px] font-semibold text-gh-accent uppercase tracking-wider px-3 py-1.5 mt-3">
                  邮箱账户
                </div>
                <EndpointRow method="POST" path="/email-accounts" desc="添加邮箱账户" />
                <EndpointRow method="GET" path="/email-accounts" desc="账户列表" />
                <EndpointRow method="POST" path="/email-accounts/:id/aliases" desc="添加别名" />

                <div className="text-[11px] font-semibold text-gh-accent uppercase tracking-wider px-3 py-1.5 mt-3">
                  临时邮箱
                </div>
                <EndpointRow method="POST" path="/temp-mail/cf/mailboxes" desc="创建临时邮箱" />
                <EndpointRow method="GET" path="/temp-mail/:id/messages" desc="查看消息" />
                <EndpointRow method="GET" path="/temp-mail/:id/codes" desc="提取验证码" />
                <EndpointRow
                  method="GET"
                  path="/temp-mail/:id/verification-links"
                  desc="提取验证链接"
                />
              </div>
            </div>
          )}

          {tab === "examples" && (
            <div className="space-y-5">
              <div>
                <h3 className="text-sm font-semibold text-gh-text mb-2">Python (requests)</h3>
                <CodeBlock
                  language="python"
                  code={`import requests

BASE = "${baseUrl}"
TOKEN = "${token}"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# 列出所有可用邮箱
r = requests.get(f"{BASE}/usable-emails", headers=HEADERS)
print(r.json())

# 读取某个邮箱的验证码
email_id = 1
r = requests.post(f"{BASE}/usable-emails/{email_id}/verification/read", headers=HEADERS)
for m in r.json()["matches"]:
    print(f"Code: {m['code']}, Link: {m['link']}")

# 为项目领取邮箱池中的邮箱
r = requests.post(f"{BASE}/mail-pool/claim",
    headers=HEADERS,
    json={"project_key": "my-project"})
print("Claimed:", r.json()["usable_email"]["address"])`}
                />
              </div>

              <div>
                <h3 className="text-sm font-semibold text-gh-text mb-2">TypeScript (fetch)</h3>
                <CodeBlock
                  language="typescript"
                  code={`const BASE = "${baseUrl}"
const TOKEN = "${token}"

async function getCodes(emailId: number) {
  const res = await fetch(\`\${BASE}/usable-emails/\${emailId}/verification/read\`, {
    method: "POST",
    headers: { Authorization: \`Bearer \${TOKEN}\` }
  })
  const data = await res.json()
  return data.matches.map((m: any) => m.code).filter(Boolean)
}

const codes = await getCodes(1)
console.log("验证码:", codes)`}
                />
              </div>

              <div>
                <h3 className="text-sm font-semibold text-gh-text mb-2">cURL</h3>
                <CodeBlock
                  language="bash"
                  code={`# 创建平台
curl -X POST ${baseUrl}/platforms \\
  -H "Authorization: Bearer ${token}" \\
  -H "Content-Type: application/json" \\
  -d '{"name":"GitHub"}'

# 绑定邮箱到平台
curl -X POST ${baseUrl}/usable-emails/1/platform-bindings \\
  -H "Authorization: Bearer ${token}" \\
  -H "Content-Type: application/json" \\
  -d '{"platform_id":1,"status":"active","notes":"主账号"}'`}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
