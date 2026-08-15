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
