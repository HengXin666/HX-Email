import { useCallback, useEffect, useRef, useState } from "react";
import { copyToClipboard } from "../utils/clipboard";

interface UseCopyToClipboardReturn {
  copied: boolean;
  copy: (text: string) => Promise<void>;
}

/**
 * Hook for copy-to-clipboard with auto-reset "copied" state.
 */
export function useCopyToClipboard(timeout = 2000): UseCopyToClipboardReturn {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const copy = useCallback(
    async (text: string) => {
      const copiedToClipboard = await copyToClipboard(text);
      if (!copiedToClipboard) return;
      setCopied(true);
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setCopied(false), timeout);
    },
    [timeout],
  );

  useEffect(() => {
    return () => clearTimeout(timerRef.current);
  }, []);

  return { copied, copy };
}
