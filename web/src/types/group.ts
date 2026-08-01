export interface Group {
  id: number;
  name: string;
  color: string;
  proxy_url?: string;
  notify_enabled?: boolean;
  polling_enabled?: boolean;
  count?: number;
}

export interface Tag {
  id: number;
  name: string;
  color: string;
}
