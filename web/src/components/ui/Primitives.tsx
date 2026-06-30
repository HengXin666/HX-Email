import { AnimatePresence, motion } from "framer-motion";
import React from "react";
import { IconX } from "../icons";
import { Spinner } from "./Spinner";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
}

export const Modal: React.FC<ModalProps> = ({
  open,
  onClose,
  title,
  children,
  footer,
  size = "md",
}) => {
  const widthClass =
    size === "sm"
      ? "max-w-sm"
      : size === "lg"
        ? "max-w-2xl"
        : size === "xl"
          ? "max-w-4xl"
          : "max-w-lg";

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.95, opacity: 0, y: 20 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className={`w-full ${widthClass} bg-gh-canvas-subtle border border-gh-border rounded-xl shadow-2xl overflow-hidden flex flex-col`}
            style={{ maxHeight: "calc(100vh - 2rem)" }}
            onClick={(e) => e.stopPropagation()}
          >
            {title && (
              <div className="flex items-center justify-between px-5 py-3 border-b border-gh-border flex-shrink-0">
                <h3 className="text-base font-semibold text-gh-text">{title}</h3>
                <button
                  onClick={onClose}
                  className="p-1 rounded-md text-gh-text-muted hover:text-gh-text hover:bg-gh-border/50 transition-colors"
                >
                  <IconX size={18} />
                </button>
              </div>
            )}
            <div className="px-5 py-4 overflow-y-auto flex-1">{children}</div>
            {footer && (
              <div className="px-5 py-3 bg-gh-canvas-inset border-t border-gh-border flex justify-end gap-2 flex-shrink-0">
                {footer}
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost" | "subtle";
  size?: "sm" | "md";
  loading?: boolean;
  icon?: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  variant = "secondary",
  size = "md",
  loading,
  icon,
  children,
  className = "",
  disabled,
  ...props
}) => {
  const base =
    "inline-flex items-center justify-center gap-2 font-medium rounded-md transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-offset-gh-canvas focus:ring-gh-accent/50 active:scale-[0.98]";

  const variants = {
    primary: "bg-gh-accent text-white hover:brightness-110 shadow-sm shadow-gh-accent/20",
    secondary:
      "bg-gh-canvas-subtle border border-gh-border text-gh-text hover:border-gh-text-muted hover:bg-gh-border/30",
    danger: "bg-gh-danger/10 border border-gh-danger/40 text-gh-danger hover:bg-gh-danger/20",
    ghost: "text-gh-text-muted hover:text-gh-text hover:bg-gh-border/40",
    subtle: "bg-gh-border/30 text-gh-text hover:bg-gh-border/50",
  };

  const sizes = {
    sm: "px-2.5 py-1 text-xs",
    md: "px-3 py-1.5 text-sm",
  };

  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={`${base} ${variants[variant]} ${sizes[size]} ${className}`}
    >
      {loading ? <Spinner size={16} /> : icon}
      {children}
    </button>
  );
};

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
}

export const Input: React.FC<InputProps> = ({ id, label, hint, className = "", ...props }) => {
  const generatedId = React.useId();
  const inputId = id ?? generatedId;

  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={inputId} className="text-xs font-medium text-gh-text-muted">
          {label}
        </label>
      )}
      <input
        {...props}
        id={inputId}
        className={`bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-1.5 text-sm text-gh-text placeholder-gh-text-secondary focus:outline-none focus:border-gh-accent focus:ring-1 focus:ring-gh-accent/50 transition-colors ${className}`}
      />
      {hint && <span className="text-xs text-gh-text-secondary">{hint}</span>}
    </div>
  );
};

interface BadgeProps {
  children: React.ReactNode;
  color?: string;
  className?: string;
  onClick?: () => void;
}

export const Badge: React.FC<BadgeProps> = ({ children, color, className = "", onClick }) => (
  <span
    onClick={onClick}
    className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full border transition-all ${
      onClick ? "cursor-pointer hover:brightness-125" : ""
    } ${className}`}
    style={
      color
        ? {
            backgroundColor: color + "20",
            borderColor: color + "40",
            color,
          }
        : undefined
    }
  >
    {children}
  </span>
);

interface CardProps {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
  selected?: boolean;
}

// ========== Checkbox ==========

interface CheckboxProps {
  label?: React.ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
  id?: string;
  disabled?: boolean;
  title?: string;
  className?: string;
  labelClassName?: string;
}

export const Checkbox: React.FC<CheckboxProps> = ({
  label,
  checked,
  onChange,
  id,
  disabled = false,
  title,
  className = "",
  labelClassName = "",
}) => {
  const generatedId = React.useId();
  const checkboxId = id ?? generatedId;

  return (
    <label
      htmlFor={checkboxId}
      title={title}
      className={`inline-flex items-center gap-2.5 group select-none ${
        disabled ? "cursor-not-allowed opacity-55" : "cursor-pointer"
      } ${className}`}
    >
      <input
        id={checkboxId}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="sr-only peer"
      />
      <span
        className={`relative w-4 h-4 rounded-md border flex items-center justify-center flex-shrink-0 transition-all duration-150 ${
          checked
            ? "bg-gh-accent border-gh-accent shadow-[0_0_0_3px_rgba(88,166,255,0.14)]"
            : "border-gh-border bg-gh-canvas-inset shadow-inner shadow-black/10 group-hover:border-gh-text-muted group-hover:bg-gh-border/20"
        } peer-focus-visible:ring-2 peer-focus-visible:ring-gh-accent/40 peer-focus-visible:ring-offset-1 peer-focus-visible:ring-offset-gh-canvas`}
      >
        {checked && (
          <svg
            width="11"
            height="11"
            viewBox="0 0 24 24"
            fill="none"
            stroke="white"
            strokeWidth="3.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="20 6 9 17 4 12" />
          </svg>
        )}
      </span>
      {label && (
        <span
          className={`text-sm text-gh-text-secondary group-hover:text-gh-text transition-colors ${labelClassName}`}
        >
          {label}
        </span>
      )}
    </label>
  );
};

// ========== Select ==========

interface SelectOption {
  value: string | number;
  label: string;
  disabled?: boolean;
}

interface SelectProps {
  label?: string;
  value: string | number;
  onChange: (value: string) => void;
  options: SelectOption[];
  id?: string;
  disabled?: boolean;
  className?: string;
  selectClassName?: string;
}

export const Select: React.FC<SelectProps> = ({
  label,
  value,
  onChange,
  options,
  id,
  disabled = false,
  className = "",
  selectClassName = "",
}) => {
  const generatedId = React.useId();
  const selectId = id ?? `select-${generatedId}`;

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      {label && (
        <label htmlFor={selectId} className="text-xs font-medium text-gh-text-muted">
          {label}
        </label>
      )}
      <div className="relative group/select">
        <select
          id={selectId}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className={`w-full appearance-none rounded-lg border border-gh-border bg-gh-canvas-inset px-3 py-2 pr-9 text-sm text-gh-text shadow-inner shadow-black/10 transition-all duration-150 cursor-pointer hover:border-gh-text-muted hover:bg-gh-border/20 focus:outline-none focus:border-gh-accent focus:ring-2 focus:ring-gh-accent/25 disabled:cursor-not-allowed disabled:opacity-55 ${selectClassName}`}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value} disabled={opt.disabled}>
              {opt.label}
            </option>
          ))}
        </select>
        <div className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-gh-text-muted transition-colors group-hover/select:text-gh-text-secondary">
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </div>
      </div>
    </div>
  );
};

export const Card: React.FC<CardProps> = ({ children, className = "", onClick, selected }) => (
  <motion.div
    whileHover={onClick ? { y: -1 } : undefined}
    whileTap={onClick ? { scale: 0.99 } : undefined}
    onClick={onClick}
    className={`rounded-lg border transition-all ${
      selected
        ? "border-gh-accent bg-gh-accent/5 shadow-[0_0_0_1px_rgba(88,166,255,0.3)]"
        : "border-gh-border bg-gh-canvas-subtle hover:border-gh-text-muted"
    } ${onClick ? "cursor-pointer" : ""} ${className}`}
  >
    {children}
  </motion.div>
);
