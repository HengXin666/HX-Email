export interface Group {
  id: number;
  name: string;
  color: string;
  proxy_url?: string;
  notify_enabled?: boolean;
  polling_enabled?: boolean;
  allowed_provider?: string;
  count?: number;
  account_count?: number;
  valid_token_count?: number;
}

export interface Tag {
  id: number;
  name: string;
  color: string;
}

interface GroupTokenBucket {
  account_count: number;
  oauth_account_count: number;
  valid_token_count: number;
  invalid_token_count: number;
}

interface GroupTokenStatusGroup {
  id: number;
  name: string;
  color: string;
  proxy_url: string;
  allowed_provider: string;
  account_count: number;
  oauth_account_count: number;
  valid_token_count: number;
  invalid_token_count: number;
}

export interface GroupTokenStatus {
  groups: GroupTokenStatusGroup[];
  ungrouped: GroupTokenBucket;
}
