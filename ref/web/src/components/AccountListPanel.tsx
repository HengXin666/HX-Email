import React, { useState, useEffect, useRef } from 'react';
import { EmailAccount, EmailGroup } from '../types';
import { CopyIcon, KeyIcon, EllipsisIcon, PlusIcon, MailIcon, CheckIcon, XIcon, EditIcon, TrashIcon, StarIcon } from './Icons';
import { showToast } from './Toast';

interface AccountListPanelProps {
  group: EmailGroup | null;
  accounts: EmailAccount[];
  selectedAccountId: string | null;
  onSelectAccount: (id: string) => void;
  onAddAccount: (groupId: string, primaryEmail: string, label: string) => void;
  onDeleteAccount: (id: string) => void;
  onUpdateAccount: (id: string, updates: Partial<EmailAccount>) => void;
  onGetVerificationCode: (accountId: string) => void;
}

export const AccountListPanel: React.FC<AccountListPanelProps> = ({
  group,
  accounts,
  selectedAccountId,
  onSelectAccount,
  onAddAccount,
  onDeleteAccount,
  onUpdateAccount,
  onGetVerificationCode,
}) => {
  const [isAdding, setIsAdding] = useState(false);
  const [newEmail, setNewEmail] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [showAliases, setShowAliases] = useState<Record<string, boolean>>({});
  const [editingAliasId, setEditingAliasId] = useState<string | null>(null);
  const [aliasInput, setAliasInput] = useState('');
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuOpenId && menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpenId(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [menuOpenId]);

  const handleCopy = (email: string) => {
    navigator.clipboard.writeText(email).then(() => {
      showToast(`已复制: ${email}`);
    }).catch(() => {
      showToast('复制失败', 'error');
    });
  };

  const handleAdd = () => {
    if (!newEmail.trim() || !group) return;
    if (!newEmail.includes('@')) {
      showToast('请输入有效的邮箱地址', 'error');
      return;
    }
    onAddAccount(group.id, newEmail.trim(), newLabel.trim());
    setNewEmail('');
    setNewLabel('');
    setIsAdding(false);
    showToast('账号添加成功');
  };

  const handleAddAlias = (accountId: string) => {
    if (!aliasInput.trim() || !aliasInput.includes('@')) {
      showToast('请输入有效的邮箱地址', 'error');
      return;
    }
    const account = accounts.find((a) => a.id === accountId);
    if (account) {
      onUpdateAccount(accountId, { aliasEmails: [...account.aliasEmails, aliasInput.trim()] });
      showToast('别名添加成功');
    }
    setAliasInput('');
    setEditingAliasId(null);
  };

  const handleRemoveAlias = (accountId: string, alias: string) => {
    const account = accounts.find((a) => a.id === accountId);
    if (account) {
      onUpdateAccount(accountId, { aliasEmails: account.aliasEmails.filter((a) => a !== alias) });
      showToast('别名已移除');
    }
  };

  const handleDelete = (id: string) => {
    onDeleteAccount(id);
    setDeleteConfirmId(null);
    setMenuOpenId(null);
    showToast('账号已删除');
  };

  const toggleAliases = (accountId: string) => {
    setShowAliases((prev) => ({ ...prev, [accountId]: !prev[accountId] }));
  };

  if (!group) {
    return (
      <div className="w-[320px] min-w-[320px] h-full bg-[#010409] border-r border-[#21262d] flex items-center justify-center">
        <div className="text-center text-[#484f58] animate-fade-in">
          <MailIcon size={40} className="mx-auto mb-3 text-[#21262d]" />
          <p className="text-sm">选择一个分组查看账号</p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-[320px] min-w-[320px] h-full bg-[#010409] border-r border-[#21262d] flex flex-col">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#21262d]">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <div
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: group.color }}
            />
            <h2 className="text-[#f0f6fc] font-semibold text-sm">{group.name}</h2>
          </div>
          <button
            onClick={() => setIsAdding(true)}
            className="p-1 rounded-md text-[#8b949e] hover:text-[#f0f6fc] hover:bg-[#21262d] transition-all duration-200"
            title="添加账号"
          >
            <PlusIcon size={16} />
          </button>
        </div>
        <p className="text-[#484f58] text-xs">{accounts.length} 个账号</p>
      </div>

      {/* Add new account */}
      {isAdding && (
        <div className="px-3 py-3 border-b border-[#21262d] bg-[#0d1117] animate-slide-up">
          <input
            type="text"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            placeholder="邮箱地址"
            className="w-full bg-[#0d1117] border border-[#30363d] rounded-md px-2.5 py-1.5 text-sm text-[#f0f6fc] placeholder-[#484f58] focus:border-[#58a6ff] focus:outline-none transition-colors mb-2"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleAdd();
              if (e.key === 'Escape') setIsAdding(false);
            }}
          />
          <input
            type="text"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            placeholder="备注名（可选）"
            className="w-full bg-[#0d1117] border border-[#30363d] rounded-md px-2.5 py-1.5 text-sm text-[#f0f6fc] placeholder-[#484f58] focus:border-[#58a6ff] focus:outline-none transition-colors mb-2"
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleAdd();
              if (e.key === 'Escape') setIsAdding(false);
            }}
          />
          <div className="flex gap-1.5">
            <button
              onClick={handleAdd}
              className="flex-1 px-2 py-1.5 bg-[#238636] text-white rounded-md text-xs hover:bg-[#2ea043] transition-colors flex items-center justify-center gap-1"
            >
              <CheckIcon size={12} /> 添加
            </button>
            <button
              onClick={() => {
                setIsAdding(false);
                setNewEmail('');
                setNewLabel('');
              }}
              className="flex-1 px-2 py-1.5 bg-[#21262d] text-[#c9d1d9] rounded-md text-xs hover:bg-[#30363d] transition-colors flex items-center justify-center gap-1"
            >
              <XIcon size={12} /> 取消
            </button>
          </div>
        </div>
      )}

      {/* Account list */}
      <div className="flex-1 overflow-y-auto py-2 px-2">
        {accounts.map((account, index) => {
          const isSelected = selectedAccountId === account.id;
          const isShowAlias = showAliases[account.id] || false;
          const isEditingAlias = editingAliasId === account.id;

          return (
            <div
              key={account.id}
              className="animate-slide-up"
              style={{ animationDelay: `${index * 60}ms` }}
            >
              <div
                onClick={() => onSelectAccount(account.id)}
                className={`group p-3 rounded-lg cursor-pointer transition-all duration-200 mb-1.5 border ${
                  isSelected
                    ? 'bg-[#1f6feb15] border-[#1f6feb33]'
                    : 'bg-[#0d1117] border-[#21262d] hover:bg-[#161b22] hover:border-[#30363d]'
                }`}
              >
                {/* Primary email */}
                <div className="flex items-start gap-2">
                  <div
                    className="w-2 h-2 rounded-full mt-1.5 flex-shrink-0"
                    style={{ backgroundColor: group.color }}
                  />
                  <div className="flex-1 min-w-0">
                    {account.label && (
                      <div className="text-[#8b949e] text-xs mb-0.5">{account.label}</div>
                    )}
                    <div className="flex items-center gap-1.5">
                      <span className="text-[#f0f6fc] text-sm font-mono truncate flex-1">
                        {account.primaryEmail}
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleCopy(account.primaryEmail);
                        }}
                        className="p-1 rounded text-[#484f58] hover:text-[#58a6ff] hover:bg-[#1f6feb20] transition-all flex-shrink-0 opacity-0 group-hover:opacity-100"
                        title="复制邮箱"
                      >
                        <CopyIcon size={12} />
                      </button>
                    </div>
                    <div className="flex items-center gap-1 mt-0.5">
                      <StarIcon size={10} className="text-[#d29922] flex-shrink-0" />
                      <span className="text-[#d29922] text-[10px]">主账号</span>
                    </div>
                  </div>
                </div>

                {/* Alias emails toggle */}
                {account.aliasEmails.length > 0 && (
                  <div className="ml-4 mt-1.5">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleAliases(account.id);
                      }}
                      className="text-[#58a6ff] text-xs hover:text-[#79c0ff] transition-colors flex items-center gap-1"
                    >
                      <svg
                        className={`transition-transform duration-200 ${isShowAlias ? 'rotate-90' : ''}`}
                        width="10"
                        height="10"
                        viewBox="0 0 16 16"
                        fill="currentColor"
                      >
                        <path d="M6.22 3.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L9.94 8 6.22 4.28a.75.75 0 0 1 0-1.06Z" />
                      </svg>
                      {account.aliasEmails.length} 个别名
                    </button>
                  </div>
                )}

                {/* Alias emails */}
                {isShowAlias && account.aliasEmails.length > 0 && (
                  <div className="ml-4 mt-1.5 space-y-1 animate-slide-up">
                    {account.aliasEmails.map((alias, idx) => (
                      <div key={idx} className="flex items-center gap-1.5 group/alias">
                        <MailIcon size={10} className="text-[#484f58] flex-shrink-0" />
                        <span className="text-[#8b949e] text-xs font-mono truncate flex-1">{alias}</span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCopy(alias);
                          }}
                          className="p-0.5 rounded text-[#484f58] hover:text-[#58a6ff] transition-all flex-shrink-0 opacity-0 group-hover/alias:opacity-100"
                        >
                          <CopyIcon size={10} />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRemoveAlias(account.id, alias);
                          }}
                          className="p-0.5 rounded text-[#484f58] hover:text-[#f85149] transition-all flex-shrink-0 opacity-0 group-hover/alias:opacity-100"
                        >
                          <XIcon size={10} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Add alias input */}
                {isEditingAlias && (
                  <div className="ml-4 mt-1.5 animate-slide-up" onClick={(e) => e.stopPropagation()}>
                    <div className="flex gap-1">
                      <input
                        type="text"
                        value={aliasInput}
                        onChange={(e) => setAliasInput(e.target.value)}
                        placeholder="别名邮箱"
                        className="flex-1 bg-[#0d1117] border border-[#30363d] rounded px-2 py-0.5 text-xs text-[#f0f6fc] placeholder-[#484f58] focus:border-[#58a6ff] focus:outline-none"
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleAddAlias(account.id);
                          if (e.key === 'Escape') setEditingAliasId(null);
                        }}
                      />
                      <button
                        onClick={() => handleAddAlias(account.id)}
                        className="px-1.5 py-0.5 bg-[#238636] text-white rounded text-[10px] hover:bg-[#2ea043] transition-colors"
                      >
                        <CheckIcon size={10} />
                      </button>
                      <button
                        onClick={() => setEditingAliasId(null)}
                        className="px-1.5 py-0.5 bg-[#21262d] text-[#c9d1d9] rounded text-[10px] hover:bg-[#30363d] transition-colors"
                      >
                        <XIcon size={10} />
                      </button>
                    </div>
                  </div>
                )}

                {/* Bottom row: time, verification, settings */}
                <div className="flex items-center justify-between mt-2 ml-4">
                  <span className="text-[#484f58] text-[11px]">{account.lastUpdated}</span>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onGetVerificationCode(account.id);
                      }}
                      className="px-2 py-0.5 bg-[#1f6feb20] text-[#58a6ff] rounded text-[11px] hover:bg-[#1f6feb30] transition-all duration-200 flex items-center gap-1"
                    >
                      <KeyIcon size={10} /> 验证码
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingAliasId(account.id);
                      }}
                      className="px-2 py-0.5 bg-[#23863620] text-[#3fb950] rounded text-[11px] hover:bg-[#23863630] transition-all duration-200 flex items-center gap-1"
                    >
                      <PlusIcon size={10} /> 别名
                    </button>
                    <div className="relative">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setMenuOpenId(menuOpenId === account.id ? null : account.id);
                        }}
                        className="p-0.5 rounded text-[#484f58] hover:text-[#c9d1d9] hover:bg-[#21262d] transition-all"
                      >
                        <EllipsisIcon size={14} />
                      </button>
                      {/* Dropdown menu */}
                      {menuOpenId === account.id && (
                        <div ref={menuRef} className="absolute right-0 top-6 z-10 bg-[#161b22] border border-[#30363d] rounded-md shadow-lg py-1 min-w-[120px] animate-scale-in"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            onClick={() => {
                              setMenuOpenId(null);
                              setEditingAliasId(account.id);
                            }}
                            className="w-full px-3 py-1.5 text-left text-xs text-[#c9d1d9] hover:bg-[#1f6feb20] hover:text-[#58a6ff] transition-colors flex items-center gap-2"
                          >
                            <PlusIcon size={12} /> 添加别名
                          </button>
                          <button
                            onClick={() => {
                              setMenuOpenId(null);
                              handleCopy(account.primaryEmail);
                            }}
                            className="w-full px-3 py-1.5 text-left text-xs text-[#c9d1d9] hover:bg-[#1f6feb20] hover:text-[#58a6ff] transition-colors flex items-center gap-2"
                          >
                            <CopyIcon size={12} /> 复制邮箱
                          </button>
                          <div className="border-t border-[#21262d] my-1" />
                          <button
                            onClick={() => {
                              setDeleteConfirmId(account.id);
                              setMenuOpenId(null);
                            }}
                            className="w-full px-3 py-1.5 text-left text-xs text-[#f85149] hover:bg-[#da363320] transition-colors flex items-center gap-2"
                          >
                            <TrashIcon size={12} /> 删除账号
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Delete confirmation inline */}
                {deleteConfirmId === account.id && (
                  <div className="ml-4 mt-2 p-2 bg-[#da363315] border border-[#da363340] rounded-md animate-scale-in">
                    <p className="text-[#f85149] text-xs mb-1.5">确认删除此账号？</p>
                    <div className="flex gap-1">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(account.id);
                        }}
                        className="flex-1 px-2 py-0.5 bg-[#da3633] text-white rounded text-xs hover:bg-[#f85149] transition-colors"
                      >
                        删除
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteConfirmId(null);
                        }}
                        className="flex-1 px-2 py-0.5 bg-[#21262d] text-[#c9d1d9] rounded text-xs hover:bg-[#30363d] transition-colors"
                      >
                        取消
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {accounts.length === 0 && (
          <div className="py-12 text-center text-[#484f58] animate-fade-in">
            <MailIcon size={36} className="mx-auto mb-2 text-[#21262d]" />
            <p className="text-sm">此分组暂无账号</p>
            <p className="text-xs mt-1">点击 + 添加邮箱账号</p>
          </div>
        )}
      </div>
    </div>
  );
};
