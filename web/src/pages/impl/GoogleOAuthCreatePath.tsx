import React, { useState } from "react";
import { api } from "../../api/client";
import { IconCheck, IconKey } from "../../components/icons";
import { Button, Input } from "../../components/ui/Primitives";
import { useToast } from "../../components/ui/Toast";
import type { EmailAccount } from "../../types";
import { GoogleOAuthControls } from "./GoogleOAuthControls";

interface GoogleOAuthCreatePathProps {
  groupId?: number | null;
  onChanged: () => void | Promise<void>;
}

export function GoogleOAuthCreatePath({ groupId = null, onChanged }: GoogleOAuthCreatePathProps) {
  const { toast } = useToast();
  const [email, setEmail] = useState("");
  const [account, setAccount] = useState<EmailAccount | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const handleCreate = async (): Promise<void> => {
    const address = email.trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(address)) {
      toast("请输入有效的 Gmail 地址", "error");
      return;
    }
    setIsCreating(true);
    try {
      const created = await api.createEmailAccount({
        provider: "gmail",
        primary_address: address,
        display_name: address,
      });
      if (groupId) await api.updateEmailAccount(created.id, { group_id: groupId });
      setAccount(created);
      await onChanged();
      toast("Gmail 账号已创建，请继续完成 Google 授权", "success");
    } catch (error: unknown) {
      toast(error instanceof Error ? error.message : "创建 Gmail 账号失败", "error");
    } finally {
      setIsCreating(false);
    }
  };

  if (account) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 rounded-lg border border-gh-success/30 bg-gh-success/5 px-3 py-2 text-xs text-gh-success">
          <IconCheck size={13} /> 已创建 {account.primary_address}，Token
          将在授权成功后自动加密保存。
        </div>
        <GoogleOAuthControls
          accountId={account.id}
          email={account.primary_address}
          onAuthorized={onChanged}
        />
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-gh-accent/30 bg-gh-accent/5 p-4">
      <div className="mb-3 flex items-start gap-2">
        <IconKey size={15} className="mt-0.5 text-gh-accent" />
        <div>
          <div className="text-sm font-semibold text-gh-text">Google 一键授权</div>
          <p className="mt-1 text-xs leading-relaxed text-gh-text-secondary">
            先创建 Gmail 账号记录，再配置或复用 Google OAuth 客户端并授权。无需填写 Gmail 登录密码。
          </p>
        </div>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <Input
          label="Gmail 地址"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="name@gmail.com"
          className="flex-1"
        />
        <Button
          variant="primary"
          onClick={handleCreate}
          loading={isCreating}
          disabled={!email.trim()}
        >
          创建并继续授权
        </Button>
      </div>
    </div>
  );
}
