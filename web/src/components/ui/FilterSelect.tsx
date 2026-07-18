import React from "react";
import { IconFilter } from "../icons";
import { Select } from "./Primitives";

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
    <Select
      value={value}
      onChange={onChange}
      options={[{ value: "", label: placeholder }, ...options]}
      selectClassName="pl-9"
    />
    <IconComp
      size={14}
      className="absolute left-3 top-1/2 -translate-y-1/2 text-gh-text-muted pointer-events-none"
    />
  </div>
);
