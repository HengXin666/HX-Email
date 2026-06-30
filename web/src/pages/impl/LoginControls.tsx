import React from "react";

interface FloatingInputProps {
  label: string;
  ariaLabel?: string;
  type?: string;
  value: string;
  disabled: boolean;
  autoFocus?: boolean;
  error?: string;
  onChange: (value: string) => void;
}

export const FloatingInput: React.FC<FloatingInputProps> = ({
  label,
  ariaLabel,
  type = "text",
  value,
  disabled,
  autoFocus,
  error = "",
  onChange,
}) => (
  <div className="relative mb-9 w-full">
    <input
      aria-label={ariaLabel ?? label}
      type={type}
      placeholder={label}
      value={value}
      autoFocus={autoFocus}
      tabIndex={disabled ? -1 : 0}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
      className="peer h-9 w-full rounded-lg border-0 bg-transparent px-4 text-base text-[#f6f9ff] outline outline-[1.5px] outline-[#c8c8dc] transition placeholder:text-[#afb4be] focus:outline-[#e0e5f0] focus:placeholder:opacity-0 disabled:cursor-default"
    />
    <span className="pointer-events-none absolute left-0 top-0 text-xs font-bold text-[#f6f9ff] opacity-0 transition-all duration-300 peer-focus:-top-5 peer-focus:opacity-100 peer-[&:not(:placeholder-shown)]:-top-5 peer-[&:not(:placeholder-shown)]:opacity-100">
      {label}
    </span>
    {error && (
      <div className="absolute right-0 top-10 whitespace-nowrap text-right text-xs font-bold text-[#e93a3a]">
        {error}
      </div>
    )}
  </div>
);

export const AuthButton: React.FC<{
  children: React.ReactNode;
  disabled: boolean;
  loading: boolean;
}> = ({ children, disabled, loading }) => (
  <button
    type="submit"
    disabled={disabled || loading}
    className="h-9 w-full cursor-pointer border border-[#1cff5c87] bg-[#2dcd3a32] text-lg text-[#c1ff18ce] transition duration-300 hover:border-[#da0aff87] hover:bg-[#19fc7f73] hover:text-[#edff29] disabled:cursor-not-allowed disabled:border-[#fffb1c87] disabled:bg-[#bb323273] disabled:text-[#ecff18a4]"
  >
    {loading ? "处理中..." : children}
  </button>
);
