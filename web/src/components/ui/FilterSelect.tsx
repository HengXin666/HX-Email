import React from "react";
import { IconChevronDown, IconFilter } from "../icons";

interface FilterSelectProps {
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  placeholder?: string;
  icon?: React.FC<{ size?: number; className?: string }>;
  className?: string;
}

export const FilterSelect: React.FC<FilterSelectProps> = ({
  value,
  onChange,
  options,
  placeholder = "全部",
  icon: IconComp = IconFilter,
  className = "",
}) => (
  <div className={`relative ${className}`}>
    <select
      value={value}
      onChange={(e: React.ChangeEvent<HTMLSelectElement>) => onChange(e.target.value)}
      className="appearance-none bg-gh-canvas-subtle border border-gh-border rounded-lg pl-9 pr-8 py-2 text-sm text-gh-text focus:outline-none focus:border-gh-accent cursor-pointer"
    >
      <option value="">{placeholder}</option>
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
    <IconComp
      size={14}
      className="absolute left-3 top-1/2 -translate-y-1/2 text-gh-text-muted pointer-events-none"
    />
    <IconChevronDown
      size={12}
      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gh-text-muted pointer-events-none"
    />
  </div>
);
