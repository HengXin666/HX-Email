import React from "react";
import { copyToClipboard } from "../../utils/clipboard";
import { IconCheck, IconCopy } from "../icons";

interface CopyButtonProps {
  text: string;
  size?: number;
  className?: string;
  timeout?: number;
}

export const CopyButton: React.FC<CopyButtonProps> = ({
  text,
  size = 14,
  className = "",
  timeout = 2000,
}) => {
  const [copied, setCopied] = React.useState(false);
  const timerRef = React.useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const copiedToClipboard = await copyToClipboard(text);
    if (copiedToClipboard) {
      setCopied(true);
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setCopied(false), timeout);
    }
  };

  React.useEffect(() => {
    return () => clearTimeout(timerRef.current);
  }, []);

  return (
    <button
      onClick={handleCopy}
      className={`p-0.5 rounded transition-colors hover:bg-gh-border/40 ${
        copied ? "text-gh-success" : "text-gh-text-muted hover:text-gh-text"
      } ${className}`}
      title={copied ? "已复制" : "复制"}
    >
      {copied ? <IconCheck size={size} /> : <IconCopy size={size} />}
    </button>
  );
};
