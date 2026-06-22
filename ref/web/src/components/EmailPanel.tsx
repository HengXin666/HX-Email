import React from 'react';
import { Email, EmailAccount, EmailGroup } from '../types';
import { MailIcon, KeyIcon, CopyIcon, StarIcon } from './Icons';
import { showToast } from './Toast';

interface EmailPanelProps {
  account: EmailAccount | null;
  group: EmailGroup | null;
  emails: Email[];
  onGetVerificationCode: (accountId: string) => void;
}

export const EmailPanel: React.FC<EmailPanelProps> = ({
  account,
  group,
  emails,
  onGetVerificationCode,
}) => {
  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      showToast(`已复制: ${text}`);
    }).catch(() => {
      showToast('复制失败', 'error');
    });
  };

  if (!account || !group) {
    return (
      <div className="flex-1 h-full bg-[#0d1117] flex items-center justify-center">
        <div className="text-center text-[#484f58] animate-fade-in">
          <MailIcon size={48} className="mx-auto mb-3 text-[#21262d]" />
          <p className="text-sm">选择一个账号查看邮件</p>
        </div>
      </div>
    );
  }

  const primaryEmails = emails.filter((e) => e.type === 'primary');
  const aliasEmails = emails.filter((e) => e.type === 'alias');

  return (
    <div className="flex-1 h-full bg-[#0d1117] flex flex-col overflow-hidden">
      {/* Account header */}
      <div className="px-5 py-4 border-b border-[#21262d] animate-slide-up">
        <div className="flex items-center gap-3 mb-2">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: `${group.color}25` }}
          >
            <span style={{ color: group.color }}><MailIcon size={18} /></span>
          </div>
          <div>
            {account.label && (
              <div className="text-[#8b949e] text-xs">{account.label}</div>
            )}
            <div className="flex items-center gap-2">
              <span className="text-[#f0f6fc] font-mono text-sm">{account.primaryEmail}</span>
              <StarIcon size={12} className="text-[#d29922]" />
              <span className="text-[#d29922] text-[10px]">主账号</span>
            </div>
          </div>
        </div>

        {/* Alias emails list */}
        {account.aliasEmails.length > 0 && (
          <div className="mt-2 space-y-1">
            {account.aliasEmails.map((alias, idx) => (
              <div key={idx} className="flex items-center gap-2 group/alias">
                <MailIcon size={10} className="text-[#484f58]" />
                <span className="text-[#8b949e] text-xs font-mono">{alias}</span>
                <span className="text-[#484f58] text-[10px]">别名</span>
                <button
                  onClick={() => handleCopy(alias)}
                  className="p-0.5 rounded text-[#484f58] hover:text-[#58a6ff] transition-all opacity-0 group-hover/alias:opacity-100"
                >
                  <CopyIcon size={10} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 mt-3">
          <button
            onClick={() => {
              onGetVerificationCode(account.id);
            }}
            className="px-3 py-1.5 bg-[#1f6feb] text-white rounded-md text-xs hover:bg-[#388bfd] transition-all duration-200 flex items-center gap-1.5"
          >
            <KeyIcon size={12} /> 获取验证码
          </button>
          <button
            onClick={() => handleCopy(account.primaryEmail)}
            className="px-3 py-1.5 bg-[#21262d] text-[#c9d1d9] rounded-md text-xs hover:bg-[#30363d] transition-all duration-200 flex items-center gap-1.5 border border-[#30363d]"
          >
            <CopyIcon size={12} /> 复制邮箱
          </button>
        </div>
      </div>

      {/* Email list */}
      <div className="flex-1 overflow-y-auto">
        {/* Primary emails */}
        {primaryEmails.length > 0 && (
          <div className="px-4 py-3">
            <div className="text-[#8b949e] text-xs font-medium mb-2 flex items-center gap-1.5">
              <StarIcon size={10} className="text-[#d29922]" />
              主账号邮件
              <span className="text-[#484f58]">({primaryEmails.length})</span>
            </div>
            <div className="space-y-1.5">
              {primaryEmails.map((email, index) => (
                <EmailCard key={email.id} email={email} index={index} onCopy={handleCopy} />
              ))}
            </div>
          </div>
        )}

        {/* Alias emails */}
        {aliasEmails.length > 0 && (
          <div className="px-4 py-3 border-t border-[#21262d]">
            <div className="text-[#8b949e] text-xs font-medium mb-2 flex items-center gap-1.5">
              <MailIcon size={10} className="text-[#58a6ff]" />
              别名邮件
              <span className="text-[#484f58]">({aliasEmails.length})</span>
            </div>
            <div className="space-y-1.5">
              {aliasEmails.map((email, index) => (
                <EmailCard key={email.id} email={email} index={index} onCopy={handleCopy} />
              ))}
            </div>
          </div>
        )}

        {emails.length === 0 && (
          <div className="py-16 text-center text-[#484f58] animate-fade-in">
            <MailIcon size={40} className="mx-auto mb-2 text-[#21262d]" />
            <p className="text-sm">暂无邮件</p>
            <p className="text-xs mt-1">点击"获取验证码"查看最新邮件</p>
          </div>
        )}
      </div>
    </div>
  );
};

const EmailCard: React.FC<{
  email: Email;
  index: number;
  onCopy: (text: string) => void;
}> = ({ email, index, onCopy }) => {
  const [expanded, setExpanded] = React.useState(false);

  return (
    <div
      className={`p-3 rounded-lg border transition-all duration-200 cursor-pointer animate-slide-up relative ${
        email.read
          ? 'bg-[#0d1117] border-[#21262d] hover:bg-[#161b22]'
          : 'bg-[#1f6feb08] border-[#1f6feb20] hover:bg-[#1f6feb12]'
      }`}
      style={{ animationDelay: `${index * 50}ms` }}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-start gap-2">
        <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${email.read ? 'bg-[#30363d]' : 'bg-[#58a6ff]'}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-0.5">
            <span className={`text-sm truncate ${email.read ? 'text-[#8b949e]' : 'text-[#f0f6fc] font-medium'}`}>
              {email.from}
            </span>
            <span className="text-[#484f58] text-[11px] flex-shrink-0 ml-2">{email.date}</span>
          </div>
          <div className={`text-sm truncate ${email.read ? 'text-[#8b949e]' : 'text-[#c9d1d9]'}`}>
            {email.subject}
          </div>
          {expanded && (
            <div className="mt-2 pt-2 border-t border-[#21262d] animate-slide-up">
              <p className="text-[#8b949e] text-sm leading-relaxed whitespace-pre-line">{email.preview}</p>
              {email.aliasEmail && (
                <div className="mt-2 flex items-center gap-1.5">
                  <MailIcon size={10} className="text-[#58a6ff]" />
                  <span className="text-[#58a6ff] text-xs font-mono">{email.aliasEmail}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onCopy(email.aliasEmail!);
                    }}
                    className="p-0.5 rounded text-[#484f58] hover:text-[#58a6ff] transition-all"
                  >
                    <CopyIcon size={10} />
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
