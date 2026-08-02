import type { EmailAccount } from "../../types";

export type Toast = (message: string, type?: "success" | "error" | "info") => void;

interface SettingsUser {
  is_admin: boolean;
  username: string;
}

export interface SettingsTabProps {
  settings: Record<string, string>;
  setSetting: (key: string, value: string) => void;
  toast: Toast;
  user: SettingsUser | null;
  accounts: EmailAccount[];
}

export interface TestOutcome {
  success: boolean;
  message: string;
}
