export interface StoredLoginPrefs {
  username: string;
  password: string;
  rememberPassword: boolean;
  autoLogin: boolean;
}

const DEFAULT_PREFS: StoredLoginPrefs = {
  username: "",
  password: "",
  rememberPassword: false,
  autoLogin: false,
};

function getStorageValue(key: string): string | null {
  try {
    return window.localStorage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function setStorageValue(key: string, value: string): void {
  try {
    window.localStorage?.setItem(key, value);
  } catch {}
}

function removeStorageValue(key: string): void {
  try {
    window.localStorage?.removeItem(key);
  } catch {}
}

export function getStoredPrefs(): StoredLoginPrefs {
  const rememberPassword = getStorageValue("hx_remember_password") === "true";
  const autoLogin = getStorageValue("hx_auto_login") === "true";
  const username = getStorageValue("hx_last_username") ?? DEFAULT_PREFS.username;
  const storedPassword = getStorageValue("hx_password");

  return {
    username,
    password: rememberPassword && storedPassword ? storedPassword : DEFAULT_PREFS.password,
    rememberPassword,
    autoLogin: autoLogin && rememberPassword && Boolean(storedPassword),
  };
}

export function persistLoginPrefs(
  username: string,
  password: string,
  rememberPassword: boolean,
  autoLogin: boolean,
): void {
  setStorageValue("hx_last_username", username);
  setStorageValue("hx_remember_password", String(rememberPassword));
  setStorageValue("hx_auto_login", String(autoLogin && rememberPassword));
  if (rememberPassword) {
    setStorageValue("hx_password", password);
  } else {
    removeStorageValue("hx_password");
  }
}
