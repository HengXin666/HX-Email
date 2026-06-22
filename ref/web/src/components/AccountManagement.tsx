import React, { useState, useCallback } from 'react';
import { EmailGroup, EmailAccount, Email } from '../types';
import { GroupPanel } from './GroupPanel';
import { AccountListPanel } from './AccountListPanel';
import { EmailPanel } from './EmailPanel';
import { showToast } from './Toast';

// Sample data
const initialGroups: EmailGroup[] = [
  { id: 'g1', name: '工作邮箱', color: '#1f6feb' },
  { id: 'g2', name: '个人邮箱', color: '#238636' },
  { id: 'g3', name: '社交平台', color: '#8957e5' },
  { id: 'g4', name: '开发相关', color: '#d29922' },
  { id: 'g5', name: '临时注册', color: '#f78166' },
];

const initialAccounts: EmailAccount[] = [
  {
    id: 'a1', groupId: 'g1', primaryEmail: 'zhang@company.com',
    aliasEmails: ['zhangsan@company.com', 'z.s@company.com'],
    lastUpdated: '2分钟前', label: '张工'
  },
  {
    id: 'a2', groupId: 'g1', primaryEmail: 'admin@company.com',
    aliasEmails: ['administrator@company.com'],
    lastUpdated: '15分钟前', label: '管理员'
  },
  {
    id: 'a3', groupId: 'g1', primaryEmail: 'hr@company.com',
    aliasEmails: [],
    lastUpdated: '1小时前', label: '人事'
  },
  {
    id: 'a4', groupId: 'g2', primaryEmail: 'myself@gmail.com',
    aliasEmails: ['me@gmail.com', 'personal@gmail.com'],
    lastUpdated: '30分钟前'
  },
  {
    id: 'a5', groupId: 'g2', primaryEmail: 'hello@outlook.com',
    aliasEmails: ['hi@outlook.com'],
    lastUpdated: '2小时前'
  },
  {
    id: 'a6', groupId: 'g3', primaryEmail: 'user@twitter.com',
    aliasEmails: [],
    lastUpdated: '5分钟前', label: 'Twitter'
  },
  {
    id: 'a7', groupId: 'g3', primaryEmail: 'dev@reddit.com',
    aliasEmails: ['mod@reddit.com'],
    lastUpdated: '20分钟前', label: 'Reddit'
  },
  {
    id: 'a8', groupId: 'g3', primaryEmail: 'photo@instagram.com',
    aliasEmails: [],
    lastUpdated: '1小时前', label: 'Instagram'
  },
  {
    id: 'a9', groupId: 'g4', primaryEmail: 'dev@github.com',
    aliasEmails: ['noreply@github.com'],
    lastUpdated: '刚刚', label: 'GitHub'
  },
  {
    id: 'a10', groupId: 'g4', primaryEmail: 'ci@jenkins.io',
    aliasEmails: [],
    lastUpdated: '3小时前', label: 'Jenkins'
  },
  {
    id: 'a11', groupId: 'g5', primaryEmail: 'temp123@guerrillamail.com',
    aliasEmails: [],
    lastUpdated: '10分钟前'
  },
  {
    id: 'a12', groupId: 'g5', primaryEmail: 'throwaway@tempmail.org',
    aliasEmails: ['temp2@tempmail.org'],
    lastUpdated: '45分钟前'
  },
];

const initialEmails: Email[] = [
  { id: 'e1', accountId: 'a1', from: 'GitHub', subject: '[GitHub] Your verification code is 847291', preview: 'Your verification code is 847291. This code will expire in 10 minutes. If you did not request this code, please ignore this email.\n\nThanks,\nThe GitHub Team', date: '2分钟前', read: false, type: 'primary' },
  { id: 'e2', accountId: 'a1', from: 'Jenkins CI', subject: 'Build #1234 passed - main', preview: 'Build main #1234 has completed successfully. All tests passed. View the full report at https://jenkins.company.com/job/main/1234', date: '15分钟前', read: false, type: 'primary' },
  { id: 'e3', accountId: 'a1', from: 'Slack', subject: '[Slack] You have 3 new messages', preview: 'You have 3 new messages in #engineering channel from @alice and @bob. Click here to view them.', date: '1小时前', read: true, type: 'primary' },
  { id: 'e4', accountId: 'a1', from: 'Google', subject: 'Your verification code is 503826', preview: 'G-503826 is your Google verification code. Don\'t share it with anyone.', date: '30分钟前', read: false, type: 'alias', aliasEmail: 'zhangsan@company.com' },
  { id: 'e5', accountId: 'a1', from: 'AWS', subject: 'AWS Notification - Your instance is running', preview: 'Your EC2 instance i-1234567890abcdef0 is running. You incurred $0.05 in charges today.', date: '2小时前', read: true, type: 'alias', aliasEmail: 'z.s@company.com' },
  { id: 'e6', accountId: 'a2', from: 'Microsoft 365', subject: 'Action required: Update your password', preview: 'Your password will expire in 7 days. Please update your password to maintain access to your account.', date: '15分钟前', read: false, type: 'primary' },
  { id: 'e7', accountId: 'a2', from: 'Internal IT', subject: 'Server maintenance scheduled', preview: 'We will be performing scheduled maintenance on Saturday from 2:00 AM to 6:00 AM UTC. Services may be temporarily unavailable.', date: '3小时前', read: true, type: 'primary' },
  { id: 'e8', accountId: 'a9', from: 'GitHub', subject: '[GitHub] Verify your email address', preview: 'Please verify your email address dev@github.com by clicking the link below. This helps us ensure the security of your account.', date: '刚刚', read: false, type: 'primary' },
  { id: 'e9', accountId: 'a9', from: 'npm', subject: 'Your one-time password is 918374', preview: 'Use this code to complete your npm sign-in: 918374. This code expires in 5 minutes.', date: '5分钟前', read: false, type: 'primary' },
  { id: 'e10', accountId: 'a9', from: 'Vercel', subject: 'Deployment successful - my-app', preview: 'Your deployment for my-app has been completed successfully. Production URL: https://my-app.vercel.app', date: '1小时前', read: true, type: 'alias', aliasEmail: 'noreply@github.com' },
  { id: 'e11', accountId: 'a6', from: 'Twitter', subject: 'Your login code is 274051', preview: 'Enter this code to log in to your Twitter account: 274051. Don\'t share this code with anyone.', date: '5分钟前', read: false, type: 'primary' },
  { id: 'e12', accountId: 'a11', from: 'Signup Service', subject: 'Your verification code: 637829', preview: 'Use code 637829 to verify your account. This code expires in 15 minutes.', date: '10分钟前', read: false, type: 'primary' },
];

export const AccountManagement: React.FC = () => {
  const [groups, setGroups] = useState<EmailGroup[]>(initialGroups);
  const [accounts, setAccounts] = useState<EmailAccount[]>(initialAccounts);
  const [emails, setEmails] = useState<Email[]>(initialEmails);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>('g1');
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);

  const currentGroup = groups.find((g) => g.id === selectedGroupId) || null;
  const currentAccounts = accounts.filter((a) => a.groupId === selectedGroupId);
  const currentAccount = accounts.find((a) => a.id === selectedAccountId) || null;
  const currentEmails = emails.filter((e) => e.accountId === selectedAccountId);

  const handleAddGroup = useCallback((name: string, color: string) => {
    const newGroup: EmailGroup = {
      id: `g${Date.now()}`,
      name,
      color,
    };
    setGroups((prev) => [...prev, newGroup]);
  }, []);

  const handleUpdateGroup = useCallback((id: string, name: string, color: string) => {
    setGroups((prev) => prev.map((g) => (g.id === id ? { ...g, name, color } : g)));
  }, []);

  const handleDeleteGroup = useCallback((id: string) => {
    setGroups((prev) => prev.filter((g) => g.id !== id));
    setAccounts((prev) => prev.filter((a) => a.groupId !== id));
    if (selectedGroupId === id) {
      setSelectedGroupId(null);
      setSelectedAccountId(null);
    }
  }, [selectedGroupId]);

  const handleAddAccount = useCallback((groupId: string, primaryEmail: string, label: string) => {
    const now = new Date();
    const timeStr = `${now.getHours()}:${now.getMinutes().toString().padStart(2, '0')}`;
    const newAccount: EmailAccount = {
      id: `a${Date.now()}`,
      groupId,
      primaryEmail,
      aliasEmails: [],
      lastUpdated: `刚刚`,
      label: label || undefined,
    };
    setAccounts((prev) => [...prev, newAccount]);
  }, []);

  const handleDeleteAccount = useCallback((id: string) => {
    setAccounts((prev) => prev.filter((a) => a.id !== id));
    setEmails((prev) => prev.filter((e) => e.accountId !== id));
    if (selectedAccountId === id) {
      setSelectedAccountId(null);
    }
  }, [selectedAccountId]);

  const handleUpdateAccount = useCallback((id: string, updates: Partial<EmailAccount>) => {
    setAccounts((prev) => prev.map((a) => (a.id === id ? { ...a, ...updates } : a)));
  }, []);

  const handleGetVerificationCode = useCallback((accountId: string) => {
    const account = accounts.find((a) => a.id === accountId);
    if (!account) return;

    // Simulate getting a verification code
    const code = Math.floor(100000 + Math.random() * 900000);
    const newEmail: Email = {
      id: `e${Date.now()}`,
      accountId,
      from: '验证服务',
      subject: `您的验证码是 ${code}`,
      preview: `验证码: ${code}。此验证码将在10分钟后过期。如非本人操作，请忽略此邮件。\n\n-- 来自 MultiMail 验证码服务`,
      date: '刚刚',
      read: false,
      type: 'primary',
    };
    setEmails((prev) => [newEmail, ...prev]);

    // Copy code to clipboard
    navigator.clipboard.writeText(code.toString()).then(() => {
      showToast(`验证码 ${code} 已复制到剪贴板`);
    }).catch(() => {
      showToast(`验证码: ${code}`, 'info');
    });

    // Auto-select this account to show the email
    setSelectedAccountId(accountId);
  }, [accounts]);

  const handleSelectGroup = useCallback((id: string) => {
    setSelectedGroupId(id);
    setSelectedAccountId(null);
  }, []);

  const handleSelectAccount = useCallback((id: string) => {
    setSelectedAccountId(id);
    // Mark emails as read
    setEmails((prev) =>
      prev.map((e) => (e.accountId === id ? { ...e, read: true } : e))
    );
  }, []);

  return (
    <div className="flex h-full animate-fade-in">
      <GroupPanel
        groups={groups}
        selectedGroupId={selectedGroupId}
        onSelectGroup={handleSelectGroup}
        onAddGroup={handleAddGroup}
        onUpdateGroup={handleUpdateGroup}
        onDeleteGroup={handleDeleteGroup}
        accounts={accounts}
      />
      <AccountListPanel
        group={currentGroup}
        accounts={currentAccounts}
        selectedAccountId={selectedAccountId}
        onSelectAccount={handleSelectAccount}
        onAddAccount={handleAddAccount}
        onDeleteAccount={handleDeleteAccount}
        onUpdateAccount={handleUpdateAccount}
        onGetVerificationCode={handleGetVerificationCode}
      />
      <EmailPanel
        account={currentAccount}
        group={currentGroup}
        emails={currentEmails}
        onGetVerificationCode={handleGetVerificationCode}
      />
    </div>
  );
};
