import { type FormEvent, useState } from "react";
import { Mail, ShieldCheck } from "lucide-react";

import { Button } from "./ui/button";

type LoginScreenProps = {
  authError: string;
  registrationEnabled: boolean;
  submittingMode: "login" | "register" | null;
  onSubmit: (mode: "login" | "register", username: string, password: string) => void;
};

export function LoginScreen({
  authError,
  registrationEnabled,
  submittingMode,
  onSubmit,
}: LoginScreenProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");

  function handleLogin(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    onSubmit("login", username, password);
  }

  return (
    <main className="login-shell">
      <section className="login-layout">
        <form className="login-panel animate-rise" onSubmit={handleLogin}>
          <div className="section-heading">
            <p>欢迎回来</p>
            <h1>HX Email</h1>
            <span>登录后管理可用邮箱、验证码读取和平台绑定。</span>
          </div>
          <label className="field">
            <span>用户名</span>
            <input
              aria-label="用户名"
              onChange={(event) => setUsername(event.target.value)}
              placeholder="用户名"
              required
              type="text"
              value={username}
            />
          </label>
          <label className="field">
            <span>密码</span>
            <input
              aria-label="密码"
              onChange={(event) => setPassword(event.target.value)}
              placeholder="密码"
              required
              type="password"
              value={password}
            />
          </label>
          <Button className="w-full" disabled={submittingMode !== null} type="submit">
            <ShieldCheck size={16} />
            {submittingMode === "login" ? "登录中" : "登录"}
          </Button>
          {authError ? <p className="form-error">{authError}</p> : null}
          {registrationEnabled ? (
            <div className="registration-panel">
              <h2>注册 HX Email</h2>
              <label className="field">
                <span>新用户名</span>
                <input
                  aria-label="新用户名"
                  onChange={(event) => setNewUsername(event.target.value)}
                  placeholder="新用户名"
                  type="text"
                  value={newUsername}
                />
              </label>
              <label className="field">
                <span>新密码</span>
                <input
                  aria-label="新密码"
                  onChange={(event) => setNewPassword(event.target.value)}
                  placeholder="新密码"
                  type="password"
                  value={newPassword}
                />
              </label>
              <Button
                className="w-full"
                disabled={submittingMode !== null}
                onClick={() => onSubmit("register", newUsername, newPassword)}
                type="button"
              >
                {submittingMode === "register" ? "注册中" : "注册"}
              </Button>
            </div>
          ) : null}
        </form>
        <aside className="brand-panel animate-rise-delayed">
          <span className="brand-mark">
            <Mail size={24} />
          </span>
          <h2>Outlook Email Plus 控制台</h2>
          <p>邮箱账号、临时邮箱、邮箱池、验证码和平台绑定集中在一个工作台中。</p>
        </aside>
      </section>
    </main>
  );
}
