import type {
  RouterSubscription,
  RouterSubscriptionFilter,
  RouterWebhookStatus,
} from "../../types/messaging";

export interface SnippetInput {
  baseUrl: string;
  token: string;
  subscriptionId: number | null;
  source: string;
  webhookSecret?: string;
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

/** One-line summary of how a subscription is delivered. */
export function describeDelivery(item: Pick<RouterSubscription, "delivery" | "webhook">): string {
  if (item.delivery === "webhook") return `Webhook → ${item.webhook?.url ?? "未配置"}`;
  return "拉取 · 长轮询 / SSE / WebSocket";
}

export const WEBHOOK_STATUS_LABEL: Record<RouterWebhookStatus, string> = {
  queued: "排队中",
  sending: "投递中",
  sent: "已送达",
  held: "暂停挂起",
  failed: "失败",
  dead: "已放弃",
};

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
export function buildSnippets({
  baseUrl,
  token,
  subscriptionId,
  source,
  webhookSecret = "",
}: SnippetInput): Snippet[] {
  const id = subscriptionId ?? "<subscription_id>";
  const wsBase = baseUrl.replace(/^http/, "ws");
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
${
  typeof id === "number"
    ? `SUB = ${id}`
    : `# 还没有订阅: 先建一条, 记下 id, 之后重启也用同一个 id 续读
SUB = requests.post(f"{BASE}/router/subscriptions", headers=HEADERS,
                    json={"source": "${source || "qq:1/group"}"}).json()["id"]`
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
      key: "websocket",
      label: "WebSocket",
      language: "javascript",
      code: `// 浏览器不能给 WebSocket 设 Authorization, 令牌放在子协议 bearer.<token> 里
const ws = new WebSocket("${wsBase}/router/subscriptions/${id}/ws",
  ["hx-router", "bearer.${token}"]);
ws.onmessage = (frame) => {
  const data = JSON.parse(frame.data);
  if (data.type !== "messages") return; // 另有 ready / heartbeat / acked / error
  for (const event of data.messages) console.log(event.address, event.text);
  ws.send(JSON.stringify({ type: "ack", cursor: data.next_cursor })); // 处理完再确认
};
// 关闭码: 4401 未授权, 4404 订阅不存在, 4409 已暂停; 断线重连即从 ack 继续`,
    },
    {
      key: "webhook",
      label: "Webhook 接收端",
      language: "python",
      code: `# 新建订阅时选 Webhook, 网关把批次 POST 到你的 URL; 返回 2xx 才推进 ack,
# 失败 10 秒起翻倍重试 (上限 1 小时), 24 小时后放弃, 可在订阅页手动重投.
import hashlib, hmac, json
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = b"${webhookSecret || "<创建或轮换时显示一次的 whsec_ 密钥>"}"
seen: set[str] = set()  # 至少一次投递: 按 X-HX-Router-Delivery 去重

class Hook(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers["Content-Length"]))
        want = "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(want, self.headers.get("X-HX-Router-Signature", "")):
            self.send_response(401); self.end_headers(); return
        delivery = self.headers.get("X-HX-Router-Delivery", "")
        batch = json.loads(body)
        if delivery not in seen and batch.get("type") == "messages":
            seen.add(delivery)
            for event in batch["messages"]:
                print(event["address"], event["text"])
        self.send_response(204); self.end_headers()

HTTPServer(("0.0.0.0", 8787), Hook).serve_forever()`,
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
// 工具: subscription_create (delivery 可选 webhook) → subscription_wait → subscription_ack`,
    },
  ];
}
