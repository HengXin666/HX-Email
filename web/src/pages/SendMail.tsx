import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { IconAlertTriangle, IconCheck, IconMail, IconRefresh } from "../components/icons";
import { Topbar } from "../components/layout";
import { Button, Card, Input, Select } from "../components/ui/Primitives";
import { useToast } from "../components/ui/Toast";
import { useApp } from "../store/AppContext";
import type { SendDebugEmailResult, UsableEmail } from "../types";

const DEFAULT_SUBJECT = "HX-Email debug email";
const DEFAULT_BODY = "This is a debug email sent by HX-Email.";

function emailOptionLabel(email: UsableEmail): string {
  const state: string = email.status === "active" ? "可用" : "停用";
  const source: string = email.email_account_id ? "账号凭据" : "无账号凭据";
  return `${email.address} · ${state} · ${source}`;
}

function resultTone(result: SendDebugEmailResult): string {
  return result.success
    ? "border-gh-success/40 bg-gh-success/10"
    : "border-gh-danger/40 bg-gh-danger/10";
}

export const SendMail: React.FC = () => {
  const { emails, refreshEmails } = useApp();
  const { toast } = useToast();
  const [selectedEmailId, setSelectedEmailId] = useState<string>("");
  const [recipient, setRecipient] = useState("");
  const [subject, setSubject] = useState(DEFAULT_SUBJECT);
  const [body, setBody] = useState(DEFAULT_BODY);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<SendDebugEmailResult | null>(null);

  useEffect(() => {
    void refreshEmails();
  }, [refreshEmails]);

  const sourceEmails = useMemo(
    () =>
      emails
        .filter((email: UsableEmail) => email.status !== "archived")
        .sort((a: UsableEmail, b: UsableEmail) => a.address.localeCompare(b.address)),
    [emails],
  );

  useEffect(() => {
    if (!selectedEmailId && sourceEmails.length > 0) {
      setSelectedEmailId(String(sourceEmails[0].id));
    }
  }, [selectedEmailId, sourceEmails]);

  const selectedEmail = sourceEmails.find(
    (email: UsableEmail) => String(email.id) === selectedEmailId,
  );

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (!selectedEmail) {
      toast("请选择发件来源", "error");
      return;
    }
    const toAddress: string = recipient.trim();
    if (!toAddress) {
      toast("请填写收件人", "error");
      return;
    }
    setSending(true);
    setResult(null);
    try {
      const response: SendDebugEmailResult = await api.sendDebugEmail(selectedEmail.id, {
        recipient: toAddress,
        subject: subject.trim(),
        body: body.trim(),
      });
      setResult(response);
      toast(
        response.success ? "邮件已发送" : "发送失败，已返回处理建议",
        response.success ? "success" : "error",
      );
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "发送邮件失败", "error");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <Topbar title="发送邮件" subtitle="使用可用邮箱关联账号发送调试邮件" />
      <div className="min-h-0 flex-1 overflow-auto p-5 md:p-6 xl:p-8">
        <div className="mx-auto flex max-w-4xl flex-col gap-5">
          <Card className="p-5">
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h1 className="text-base font-semibold text-gh-text">调试邮件</h1>
                  <p className="mt-1 text-sm text-gh-text-secondary">
                    发信凭据来自所选可用邮箱关联的邮箱账号。
                  </p>
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => void refreshEmails()}
                >
                  <IconRefresh size={13} /> 刷新
                </Button>
              </div>

              <Select
                label="发件来源"
                value={selectedEmailId}
                onChange={setSelectedEmailId}
                options={sourceEmails.map((email: UsableEmail) => ({
                  value: String(email.id),
                  label: emailOptionLabel(email),
                }))}
              />
              <Input
                label="收件人"
                type="email"
                required
                value={recipient}
                onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                  setRecipient(event.target.value)
                }
                placeholder="receiver@example.com"
              />
              <Input
                label="主题"
                value={subject}
                onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                  setSubject(event.target.value)
                }
              />
              <div className="flex flex-col gap-1.5">
                <label htmlFor="send-mail-body" className="text-xs font-medium text-gh-text-muted">
                  正文
                </label>
                <textarea
                  id="send-mail-body"
                  value={body}
                  onChange={(event: React.ChangeEvent<HTMLTextAreaElement>) =>
                    setBody(event.target.value)
                  }
                  rows={8}
                  className="rounded-md border border-gh-border bg-gh-canvas-inset px-3 py-2 text-sm text-gh-text placeholder-gh-text-secondary focus:border-gh-accent focus:outline-none focus:ring-1 focus:ring-gh-accent/50"
                />
              </div>
              <div className="flex justify-end">
                <Button type="submit" variant="primary" loading={sending}>
                  <IconMail size={14} /> 发送
                </Button>
              </div>
            </form>
          </Card>

          {result && (
            <Card className={`p-5 ${resultTone(result)}`}>
              <div className="flex items-start gap-3">
                {result.success ? (
                  <IconCheck size={18} className="mt-0.5 text-gh-success" />
                ) : (
                  <IconAlertTriangle size={18} className="mt-0.5 text-gh-danger" />
                )}
                <div className="min-w-0 flex-1">
                  <h2 className="text-sm font-semibold text-gh-text">
                    {result.success ? "发送成功" : "发送失败"}
                  </h2>
                  <p className="mt-1 text-sm text-gh-text-secondary">{result.message}</p>
                  <div className="mt-3 grid gap-2 text-xs text-gh-text-secondary sm:grid-cols-2">
                    <span>发件人：{result.from_address || "-"}</span>
                    <span>SMTP：{result.smtp_host || "-"}</span>
                    <span>端口：{result.smtp_port ?? "-"}</span>
                    <span>状态：{result.code}</span>
                  </div>
                  {result.actions.length > 0 && (
                    <ul className="mt-3 list-disc space-y-1 pl-4 text-sm text-gh-text-secondary">
                      {result.actions.map((action: string) => (
                        <li key={action}>{action}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
};
