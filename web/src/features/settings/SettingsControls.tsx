import { motion } from "framer-motion";
import type React from "react";
import type { TestOutcome } from "./types";

interface SettingsToggleProps {
  enabled: boolean;
  onChange: (isEnabled: boolean) => void;
  disabled?: boolean;
}

export const SettingsToggle: React.FC<SettingsToggleProps> = ({
  enabled,
  onChange,
  disabled = false,
}) => (
  <button
    type="button"
    role="switch"
    aria-checked={enabled}
    disabled={disabled}
    onClick={() => onChange(!enabled)}
    className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
      disabled ? "cursor-not-allowed opacity-50" : ""
    } ${enabled ? "bg-gh-success" : "bg-gh-border"}`}
  >
    <motion.span
      animate={{ x: enabled ? 20 : 2 }}
      transition={{ type: "spring", stiffness: 400, damping: 30 }}
      className="absolute top-0.5 block h-5 w-5 rounded-full bg-white shadow-md"
    />
  </button>
);

export const SectionHeader: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <h4 className="mb-3 mt-1 text-xs font-semibold uppercase tracking-wider text-gh-text-muted">
    {children}
  </h4>
);

export const TestResult: React.FC<{ result: TestOutcome | null }> = ({ result }) => {
  if (!result) return null;
  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      className={`mt-2 rounded-md border px-3 py-1.5 text-xs ${
        result.success
          ? "border-gh-success/30 bg-gh-success/10 text-gh-success"
          : "border-gh-danger/30 bg-gh-danger/10 text-gh-danger"
      }`}
    >
      {result.message}
    </motion.div>
  );
};

interface ToggleRowProps extends SettingsToggleProps {
  label: string;
  description: string;
}

export const ToggleRow: React.FC<ToggleRowProps> = ({
  label,
  description,
  enabled,
  onChange,
  disabled,
}) => (
  <div className="flex items-center justify-between gap-4 rounded-md border border-gh-border bg-gh-canvas-inset p-3">
    <div className="min-w-0">
      <div className="text-sm text-gh-text">{label}</div>
      <div className="text-xs text-gh-text-secondary">{description}</div>
    </div>
    <SettingsToggle enabled={enabled} onChange={onChange} disabled={disabled} />
  </div>
);

export const SettingsTabFrame: React.FC<{
  tabKey: string;
  children: React.ReactNode;
}> = ({ tabKey, children }) => (
  <motion.div
    key={tabKey}
    initial={{ opacity: 0, y: 8 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, y: -8 }}
    transition={{ type: "spring", stiffness: 300, damping: 28 }}
    className="space-y-5"
  >
    {children}
  </motion.div>
);
