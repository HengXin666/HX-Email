import React, { useMemo, useState } from "react";
import { Card, Select } from "../../components/ui/Primitives";
import type { TokenToolAccount } from "../../types";
import { GoogleOAuthControls } from "./GoogleOAuthControls";
import { GoogleOAuthCreatePath } from "./GoogleOAuthCreatePath";

interface GoogleTokenWorkspaceProps {
  accounts: TokenToolAccount[];
  onChanged: () => void | Promise<void>;
}

export function GoogleTokenWorkspace({ accounts, onChanged }: GoogleTokenWorkspaceProps) {
  const [mode, setMode] = useState<"existing" | "create">(
    accounts.length > 0 ? "existing" : "create",
  );
  const [accountId, setAccountId] = useState(accounts[0] ? String(accounts[0].id) : "");
  const selected = useMemo(
    () => accounts.find((account) => String(account.id) === accountId),
    [accountId, accounts],
  );

  return (
    <div className="space-y-5">
      <Card className="p-5 space-y-4">
        <div>
          <h2 className="text-sm font-semibold text-gh-text">Google OAuth 一键授权</h2>
          <p className="mt-1 text-xs leading-relaxed text-gh-text-secondary">
            授权成功后，Refresh Token 会直接加密写入 Gmail 账号，不需要手动复制 Token。
          </p>
        </div>
        <Select
          label="账号操作"
          value={mode}
          onChange={(value) => setMode(value as "existing" | "create")}
          options={[
            { value: "existing", label: "授权已有 Gmail 账号", disabled: accounts.length === 0 },
            { value: "create", label: "新建 Gmail 账号并授权" },
          ]}
        />
        {mode === "existing" ? (
          <Select
            label="Gmail 账号"
            value={accountId}
            onChange={setAccountId}
            options={accounts.map((account) => ({ value: account.id, label: account.email }))}
          />
        ) : (
          <GoogleOAuthCreatePath onChanged={onChanged} />
        )}
      </Card>

      {mode === "existing" && selected && (
        <GoogleOAuthControls
          accountId={selected.id}
          email={selected.email}
          onAuthorized={onChanged}
        />
      )}
    </div>
  );
}
