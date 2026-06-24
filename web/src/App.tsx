import { useState } from "react";

import { loadWorkbenchSession, persistAccessToken, submitCredentials } from "./api";
import { LoginScreen } from "./components/LoginScreen";
import { Workbench } from "./components/Workbench";
import type { Session } from "./types";

type AppProps = {
  registrationEnabled?: boolean;
  session?: Session;
};

export function App({ registrationEnabled = false, session }: AppProps) {
  const [activeSession, setActiveSession] = useState<Session | null>(session ?? null);
  const [submittingMode, setSubmittingMode] = useState<"login" | "register" | null>(null);
  const [authError, setAuthError] = useState("");
  const [authNotice, setAuthNotice] = useState("");

  document.documentElement.classList.add("dark");

  async function handleCredentials(
    mode: "login" | "register",
    username: string,
    password: string,
  ): Promise<void> {
    setAuthError("");
    setAuthNotice("");
    setSubmittingMode(mode);
    try {
      const auth = await submitCredentials(mode, username, password);
      persistAccessToken(auth.access_token);
      const nextSession = await loadWorkbenchSession(auth.access_token, auth.user.username);
      setActiveSession(nextSession);
      setAuthNotice(mode === "login" ? "登录成功" : "注册成功");
    } catch {
      setAuthError(
        mode === "login"
          ? "用户名或密码不正确，或工作台加载失败。"
          : "注册失败，或工作台加载失败。",
      );
    } finally {
      setSubmittingMode(null);
    }
  }

  if (activeSession) {
    return <Workbench notice={authNotice} session={activeSession} />;
  }

  return (
    <LoginScreen
      authError={authError}
      onSubmit={(mode, username, password) => {
        void handleCredentials(mode, username, password);
      }}
      registrationEnabled={registrationEnabled}
      submittingMode={submittingMode}
    />
  );
}
