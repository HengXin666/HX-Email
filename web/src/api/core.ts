import type { SSERefreshEvent } from "../types";

let _sessionExpiredHandled = false;

function getStoredToken(): string | null {
  try {
    return window.localStorage?.getItem("hx_token") ?? null;
  } catch {
    return null;
  }
}

function handleSessionExpired(): void {
  if (_sessionExpiredHandled) return;
  _sessionExpiredHandled = true;
  try {
    window.sessionStorage?.setItem("hx_session_expired", "1");
  } catch {
    // sessionStorage may be unavailable
  }
  try {
    window.dispatchEvent(new CustomEvent("auth:session-expired"));
  } catch {
    // event dispatch may fail in test environments
  }
}

const API_BASE = "/api/v1";

function isNetworkFailure(error: unknown): boolean {
  return error instanceof TypeError || error instanceof DOMException;
}

function networkErrorMessage(): string {
  return "无法连接服务器，请确认后端服务已启动并且网络连接正常";
}

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  try {
    return await fetch(API_BASE + path, init);
  } catch (error) {
    if (isNetworkFailure(error)) {
      throw new Error(networkErrorMessage());
    }
    throw error;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await apiFetch(path, { ...init, headers });
  if (res.status === 401 && token) {
    handleSessionExpired();
    throw new Error("登录已过期，请重新登录");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const msg = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
    throw new Error(msg || "请求失败");
  }
  if (res.status === 204) return null as T;
  try {
    return await res.json();
  } catch {
    const text = await res.text().catch(() => "");
    throw new Error(`Invalid JSON response (status ${res.status}): ${text.slice(0, 200)}`);
  }
}

async function requestText(path: string, init: RequestInit = {}): Promise<string> {
  const token = getStoredToken();
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await apiFetch(path, { ...init, headers });
  if (res.status === 401 && token) {
    handleSessionExpired();
    throw new Error("登录已过期，请重新登录");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const msg = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
    throw new Error(msg || "请求失败");
  }
  return res.text();
}

async function streamRefresh(
  url: string,
  body?: object,
  onProgress?: (e: SSERefreshEvent) => void,
): Promise<void> {
  const token = getStoredToken();
  const res = await apiFetch(url, {
    method: body ? "POST" : "GET",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && token) {
    handleSessionExpired();
    throw new Error("登录已过期，请重新登录");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const msg = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
    throw new Error(msg || "请求失败");
  }
  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: true });
    }
    if (done) {
      buffer += decoder.decode();
      const remaining = buffer.trim();
      if (remaining.startsWith("data: ")) {
        try {
          const data: SSERefreshEvent = JSON.parse(remaining.slice(6));
          onProgress?.(data);
        } catch {
          // skip malformed final line
        }
      }
      break;
    }
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const data: SSERefreshEvent = JSON.parse(line.slice(6));
          onProgress?.(data);
        } catch {
          // skip malformed SSE lines
        }
      }
    }
  }
}

export { API_BASE, request, requestText, streamRefresh };
