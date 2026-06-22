export interface EmailGroup {
  id: string;
  name: string;
  color: string;
  isEditing?: boolean;
}

export interface EmailAccount {
  id: string;
  groupId: string;
  primaryEmail: string;
  aliasEmails: string[];
  lastUpdated: string;
  label?: string;
}

export interface Email {
  id: string;
  accountId: string;
  from: string;
  subject: string;
  preview: string;
  date: string;
  read: boolean;
  type: 'primary' | 'alias';
  aliasEmail?: string;
}

export type SidebarItem = 'overview' | 'accounts' | 'platforms' | 'tempmail' | 'api' | 'settings' | 'logout';
