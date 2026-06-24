import type {
  AuthResponse,
  EmailAccount,
  MailPoolEntry,
  Platform,
  Session,
  UsableEmail,
  WorkbenchOverview,
  WorkbenchResponse,
} from "./types";

const accessTokenStorageKey = "hx-email-token";

export function persistAccessToken(accessToken: string): void {
  try {
    window.localStorage?.setItem(accessTokenStorageKey, accessToken);
  } catch {
    // Storage can be unavailable in restricted browser contexts.
  }
}

export async function submitCredentials(
  mode: "login" | "register",
  username: string,
  password: string,
): Promise<AuthResponse> {
  const response = await fetch(mode === "login" ? "/auth/login" : "/auth/register", {
    body: JSON.stringify({ username, password }),
    headers: { "Content-Type": "application/json" },
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(mode === "login" ? "Login failed" : "Registration failed");
  }
  return (await response.json()) as AuthResponse;
}

export async function loadWorkbenchSession(
  accessToken: string,
  username: string,
): Promise<Session> {
  const [workbench, overview] = await Promise.all([
    getJson<WorkbenchResponse>("/workbench/usable-emails", accessToken),
    getJson<WorkbenchOverview>("/workbench/overview", accessToken),
  ]);
  return {
    accessToken,
    overview,
    page: workbench.page,
    pageSize: workbench.page_size,
    total: workbench.total,
    username,
    usableEmails: workbench.usable_emails.map((usableEmail) => ({
      ...usableEmail,
      platformBindingCount: usableEmail.platform_binding_count,
    })),
  };
}

export async function loadEmailAccounts(accessToken?: string): Promise<EmailAccount[]> {
  if (!accessToken) {
    return [];
  }
  const response = await getJson<{ email_accounts: EmailAccount[] }>(
    "/email-accounts",
    accessToken,
  );
  return response.email_accounts;
}

export async function loadMailPool(accessToken?: string): Promise<MailPoolEntry[]> {
  if (!accessToken) {
    return [];
  }
  const response = await getJson<{ entries: MailPoolEntry[] }>("/mail-pool/entries", accessToken);
  return response.entries;
}

export async function loadPlatforms(accessToken?: string): Promise<Platform[]> {
  if (!accessToken) {
    return [];
  }
  const response = await getJson<{ platforms: Platform[] }>("/platforms", accessToken);
  return response.platforms;
}

export async function deactivateUsableEmail(
  accessToken: string,
  usableEmailId: number,
): Promise<UsableEmail> {
  return postJson<UsableEmail>(`/usable-emails/${usableEmailId}/deactivate`, accessToken);
}

export async function readVerification(
  accessToken: string,
  usableEmailId: number,
): Promise<{ matches: { code: string | null; link: string | null; subject: string }[] }> {
  return postJson(`/usable-emails/${usableEmailId}/verification/read`, accessToken);
}

async function getJson<T>(path: string, accessToken: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${path}`);
  }
  return (await response.json()) as T;
}

async function postJson<T>(path: string, accessToken: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Authorization: `Bearer ${accessToken}` },
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${path}`);
  }
  return (await response.json()) as T;
}
