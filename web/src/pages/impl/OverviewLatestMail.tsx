import React from "react";
import { IconKey, IconMail } from "../../components/icons";
import { Badge } from "../../components/ui/Primitives";
import type { LatestMailMessage } from "../../types";
import { formatRelativeTime } from "../../utils/time";

interface OverviewLatestMailProps {
  messages: LatestMailMessage[];
  selectedEmailId: number | null;
  onSelectEmail: (emailId: number) => void;
}

function bodyPreview(message: LatestMailMessage): string {
  const compactBody: string = message.body.replace(/\s+/g, " ").trim();
  return compactBody || "无正文预览";
}

export const OverviewLatestMail: React.FC<OverviewLatestMailProps> = ({
  messages,
  selectedEmailId,
  onSelectEmail,
}) => (
  <div className="min-w-0">
    {messages.length === 0 ? (
      <div className="py-16 px-5 text-center">
        <IconMail size={24} className="mx-auto text-gh-text-muted" />
        <div className="mt-3 text-sm text-gh-text-secondary">尚未收取邮件</div>
      </div>
    ) : (
      <div className="divide-y divide-gh-border/50">
        {messages.map((message: LatestMailMessage) => {
          const isSelected: boolean = selectedEmailId === message.usable_email_id;
          return (
            <button
              key={message.id}
              type="button"
              onClick={() => onSelectEmail(message.usable_email_id)}
              className={`w-full min-w-0 px-5 py-3 text-left transition-colors ${
                isSelected ? "bg-gh-accent/10" : "hover:bg-gh-border/25"
              }`}
            >
              <span className="flex items-start gap-3 min-w-0">
                <span className="mt-0.5 w-8 h-8 rounded-md bg-gh-accent/10 text-gh-accent flex items-center justify-center shrink-0">
                  <IconMail size={14} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 min-w-0">
                    <span className="text-sm font-medium text-gh-text truncate">
                      {message.subject || "(无主题)"}
                    </span>
                    {message.verification_code && (
                      <span className="inline-flex items-center gap-1 text-xs font-mono text-gh-warning shrink-0">
                        <IconKey size={11} /> {message.verification_code}
                      </span>
                    )}
                  </span>
                  <span className="mt-0.5 block text-xs text-gh-text-secondary truncate">
                    {message.from_address || "未知发件人"} · {bodyPreview(message)}
                  </span>
                  <span className="mt-1.5 flex items-center gap-2 min-w-0">
                    <span className="text-[11px] font-mono text-gh-text-muted truncate">
                      {message.address}
                    </span>
                    {message.group && (
                      <Badge color={message.group.color || "#6e7681"}>{message.group.name}</Badge>
                    )}
                    <span className="ml-auto text-[11px] text-gh-text-muted whitespace-nowrap">
                      {formatRelativeTime(message.received_at)}
                    </span>
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
