export type MessagingChatType = "private" | "group" | "channel";

export interface MessagingCapabilities {
  supports_qr_login: boolean;
  supports_groups: boolean;
  supports_history: boolean;
  risk_level: "official" | "third_party";
  risk_notice: string;
}

export interface MessagingPluginInfo {
  key: string;
  display_name: string;
  available: boolean;
  description: string;
  capabilities: MessagingCapabilities;
}

export interface MessagingInstance {
  id: number;
  kind: string;
  name: string;
  status: string;
  config: Record<string, string>;
  capabilities?: MessagingCapabilities;
  created_at: string;
  updated_at: string;
}

export interface MessagingConversation {
  chat_id: string;
  chat_type: MessagingChatType;
  name: string;
  /** Router session address (qq:3:group:123, github:7:issue:owner/repo#42). */
  session?: string;
}

export interface MessagingMessage {
  direction: "inbound" | "outbound";
  chat_id: string;
  chat_type: MessagingChatType;
  sender_id: string;
  sender_name: string;
  text: string;
  message_id: string;
  created_at: string;
}

export interface MessagingGroup {
  group_id: string;
  name: string;
  member_count: number;
}

export interface MessagingLoginTicket {
  mode: string;
  url: string;
  qr_image_url: string;
  instructions: string;
  expires_in: number;
}

export interface MessagingLoginState {
  logged_in: boolean;
  account_id: string;
  account_name: string;
  message: string;
}

export interface MessagingLoginProbe {
  webui_reachable: boolean;
  api_reachable: boolean;
  webui_url: string;
  api_base_url: string;
  message: string;
}

export interface GithubManifestStart {
  action: string;
  state: string;
  expires_at: string;
  instance_id: number;
  manifest: unknown;
}

export interface GithubInstallation {
  id: number;
  account: string;
}

export interface GithubAppConfigSummary {
  app_id: number | string;
  app_slug: string;
  client_id: string;
  has_private_key: boolean;
  has_webhook_secret: boolean;
}

export interface GithubVerifyResult {
  verified: boolean;
  app?: string;
  installations?: GithubInstallation[];
  app_config: GithubAppConfigSummary;
}

export interface GithubAttachResult {
  attached: boolean;
  installation: GithubInstallation;
}

// ===== Router hub & persistent subscriptions (契约 v2, 阶段 2) =====

export type RouterDirection = "inbound" | "outbound" | "both";

export interface RouterSubscriptionFilter {
  direction: RouterDirection;
  kinds: string[];
  exclude_self: boolean;
  mention_self: boolean;
  contains: string;
}

export interface RouterSubscription {
  id: number;
  name: string;
  source: string;
  address: string;
  filter: RouterSubscriptionFilter;
  delivery: string;
  status: "active" | "paused";
  ack_cursor: string;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  backlog?: number;
  backlog_capped?: boolean;
}

export interface RouterSubscriptionList {
  subscriptions: RouterSubscription[];
  limit: number;
}

export interface RouterSubscriptionCreate {
  source: string;
  name?: string;
  filter?: Partial<RouterSubscriptionFilter>;
  from?: "now" | "earliest";
}

export interface RouterEvent {
  id: string;
  cursor: string;
  platform: string;
  session: string;
  address?: string;
  kind?: string;
  direction: string;
  text: string;
  sender: { id: string; name: string; is_self: boolean };
  occurred_at: string;
  flags?: Record<string, boolean | null>;
}

export interface RouterEventPage {
  messages: RouterEvent[];
  next_cursor: string;
  has_more: boolean;
  gap: boolean;
  timed_out: boolean;
  ack_cursor?: string;
  paused?: boolean;
}

export interface RouterSource {
  platform: string;
  instance_id: number;
  address: string;
  name: string;
  state: string;
  outbound: string;
}

export interface RouterHubStats {
  waiting: number;
  published: number;
}

export interface RouterApiKey {
  id: number;
  name: string;
  key_prefix: string;
  created_at: string;
  last_used_at?: string | null;
  revoked_at?: string | null;
}

export interface RouterIssuedKey extends RouterApiKey {
  key: string;
}
