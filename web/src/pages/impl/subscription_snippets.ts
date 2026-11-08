import type { RouterSubscriptionFilter } from "../../types/messaging";

export interface SnippetInput {
  baseUrl: string;
  token: string;
  subscriptionId: number | null;
  source: string;
}

export interface Snippet {
  key: string;
  label: string;
  language: string;
  code: string;
}

/** Human summary of a filter, for the subscription list. */
export function describeFilter(filter: RouterSubscriptionFilter): string {
  const parts: string[] = [
    filter.direction === "inbound" ? "入站" : filter.direction === "outbound" ? "出站" : "双向",
  ];
  if (filter.exclude_self) parts.push("排除自己");
  if (filter.mention_self) parts.push("仅 @我");
  if (filter.kinds.length) parts.push(`类型 ${filter.kinds.join("/")}`);
  if (filter.contains) parts.push(`含「${filter.contains}」`);
  return parts.join(" · ");
}

/** Quick-pick sources for one account instance (v1 whole-instance prefix + v2 selectors). */
export function sourceChoices(platform: string, instanceId: number): string[] {
  if (platform === "github")
    return [`github:${instanceId}:`, `github:${instanceId}/repo/OWNER/REPO`];
  return [
    `${platform}:${instanceId}:`,
    `${platform}:${instanceId}/group`,
    `${platform}:${instanceId}/private`,
  ];
}

/** Ready-to-paste integration code for one subscription. */
export function buildSnippets({ baseUrl, token, subscriptionId, source }: SnippetInput): Snippet[] {
  const id = subscriptionId ?? "<subscription_id>";
  const sub = `${baseUrl}/router/subscriptions/${id}`;
  const origin = baseUrl.replace(/\/api\/v1$/, "");
  return [
    {
      key: "curl",
      label: "cURL 长轮询",
      language: "bash",
      code: `# 等新消息 (最多 25 秒), 处理完再确认; 断线重连后从 ack 继续, 不丢消息
curl -s "${sub}/events?timeout_seconds=25" \\
  -H "Authorization: Bearer ${token}"

curl -s -X POST "${sub}/ack" \\
  -H "Authorization: Bearer ${token}" \\
  -H "Content-Type: application/json" \\
  -d '{"cursor":"<next_cursor>"}'`,
    },
    {
      key: "python",
      label: "Python 消费循环",
      language: "python",
      code: `import requests

BASE = "${baseUrl}"
HEADERS = {"Authorization": "Bearer ${token}"}
SUB = ${
        typeof id === "number"
          ? id
          : `None  # 先创建订阅, 或用下面这行
# SUB = requests.post(f"{BASE}/router/subscriptions", headers=HEADERS,
#                     json={"source": "${source || "qq:1/group"}"}).json()["id"]`
      }

while True:
    page = requests.get(f"{BASE}/router/subscriptions/{SUB}/events",
                        params={"timeout_seconds": 25}, headers=HEADERS, timeout=40).json()
    for event in page["messages"]:
        print(event["address"], event["sender"]["name"], event["text"])
    if page["messages"]:
        requests.post(f"{BASE}/router/subscriptions/{SUB}/ack", headers=HEADERS,
                      json={"cursor": page["next_cursor"]})`,
    },
    {
      key: "sse",
      label: "SSE 推流",
      language: "bash",
      code: `# 每条消息一帧, 帧 id 就是 cursor; 断线时带 Last-Event-ID 续上
# auto_ack=true 表示推出即确认, 适合不需要至少一次语义的看板
curl -N "${sub}/stream?auto_ack=false" \\
  -H "Authorization: Bearer ${token}"`,
    },
    {
      key: "mcp",
      label: "MCP 客户端",
      language: "json",
      code: `{
  "mcpServers": {
    "hx-router": {
      "type": "streamable-http",
      "url": "${origin}/mcp",
      "headers": { "Authorization": "Bearer ${token}" }
    }
  }
}
// 工具: subscription_create → subscription_wait → subscription_ack`,
    },
  ];
}
