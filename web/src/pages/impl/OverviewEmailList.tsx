import React from "react";
import { Badge } from "../../components/ui/Primitives";
import type { EmailAccount, UsableEmail } from "../../types";
import { formatRelativeTime } from "../../utils/time";

interface OverviewEmailListProps {
  emails: UsableEmail[];
  accounts: EmailAccount[];
  selectedEmailId: number | null;
  onSelectEmail: (emailId: number) => void;
}

function getEmailKindLabel(kind: UsableEmail["kind"]): string {
  if (kind === "primary") return "主邮箱";
  if (kind === "alias") return "别名";
  if (kind === "temp") return "临时";
  return "自定义";
}

function getEmailDisplayName(email: UsableEmail, accounts: EmailAccount[]): string {
  const account = accounts.find((item: EmailAccount) => item.id === email.email_account_id);
  return email.label || account?.display_name || email.address;
}

function getRelativeUpdatedAt(email: UsableEmail): string {
  if (!email.updated_at) return "未记录";
  return formatRelativeTime(email.updated_at);
}

export const OverviewEmailList: React.FC<OverviewEmailListProps> = ({
  emails,
  accounts,
  selectedEmailId,
  onSelectEmail,
}) => (
  <div className="min-w-0">
    <div className="px-5 py-3 border-b border-gh-border bg-gh-canvas-inset flex items-center justify-between gap-3">
      <div className="min-w-0">
        <div className="text-[11px] font-semibold text-gh-text-muted uppercase tracking-wider">
          邮箱
        </div>
        <div className="text-[11px] text-gh-text-secondary truncate">
          最近 {Math.min(emails.length, 12)} 个可用邮箱
        </div>
      </div>
      <div className="hidden sm:block text-[11px] font-semibold text-gh-text-muted uppercase tracking-wider">
        状态
      </div>
    </div>
    {emails.length === 0 ? (
      <div className="py-16 text-center text-sm text-gh-text-secondary">暂无可用邮箱</div>
    ) : (
      <div className="divide-y divide-gh-border/50">
        {emails.slice(0, 12).map((email: UsableEmail) => {
          const isSelected: boolean = selectedEmailId === email.id;
          const bindingCount: number = email.platform_binding_count ?? 0;
          return (
            <button
              key={email.id}
              type="button"
              onClick={() => onSelectEmail(email.id)}
              className={`w-full min-w-0 px-5 py-4 text-left transition-colors cursor-pointer ${
                isSelected ? "bg-gh-accent/10" : "hover:bg-gh-border/25"
              }`}
            >
              <span className="flex flex-col sm:flex-row sm:items-center gap-3 min-w-0">
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-gh-text truncate">
                    {getEmailDisplayName(email, accounts)}
                  </span>
                  <span className="mt-1 block text-xs font-mono text-gh-text-secondary truncate">
                    {email.address}
                  </span>
                </span>
                <span className="flex flex-wrap items-center gap-2 sm:justify-end sm:max-w-[260px]">
                  <Badge color={email.kind === "temp" ? "#f0883e" : "#58a6ff"}>
                    {getEmailKindLabel(email.kind)}
                  </Badge>
                  {email.group?.name && (
                    <Badge color={email.group.color ?? "#6e7681"}>{email.group.name}</Badge>
                  )}
                  <span className="text-xs text-gh-text-secondary whitespace-nowrap">
                    {bindingCount} 绑定
                  </span>
                  <span className="text-xs text-gh-text-muted whitespace-nowrap">
                    {getRelativeUpdatedAt(email)}
                  </span>
                </span>
              </span>
            </button>
          );
        })}
      </div>
    )}
  </div>
);
