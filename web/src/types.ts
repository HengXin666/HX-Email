export type EmailKind = "primary" | "alias" | "temp" | "custom";

export type EmailStatus = "active" | "inactive" | "archived";

export type UsableEmail = {
  id: number;
  address: string;
  label: string;
  kind: EmailKind;
  status: EmailStatus;
  group?: { id: number; name: string; color: string } | null;
  tags?: { id: number; name: string; color: string }[];
  platformBindingCount?: number;
};

export type Session = {
  username: string;
  accessToken?: string;
  usableEmails: UsableEmail[];
  overview?: WorkbenchOverview;
  page?: number;
  pageSize?: number;
  total?: number;
};

export type WorkbenchOverview = {
  usable_email_count: number;
  active_email_count: number;
  account_count: number;
  temp_email_count: number;
  platform_count: number;
  binding_count: number;
  pool_available_count: number;
  pool_claimed_count: number;
  verification_count: number;
};

export type AuthResponse = {
  access_token: string;
  user: {
    id: number;
    username: string;
    is_admin: boolean;
  };
};

export type WorkbenchEmailResponse = Omit<UsableEmail, "platformBindingCount"> & {
  platform_binding_count?: number;
};

export type WorkbenchResponse = {
  usable_emails: WorkbenchEmailResponse[];
  total: number;
  page: number;
  page_size: number;
};

export type EmailAccount = {
  id: number;
  provider: string;
  primary_address: string;
  display_name: string;
  status: string;
  usable_emails: UsableEmail[];
};

export type Platform = {
  id: number;
  name: string;
};

export type MailPoolEntry = {
  id: number;
  usable_email: UsableEmail;
  status: string;
  claim_key: string;
  claimed_project_key: string;
  completed_project_key: string;
};
