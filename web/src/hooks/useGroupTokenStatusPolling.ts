import { useEffect, useRef } from "react";
import { useApp } from "../store/AppContext";

/**
 * Lightweight live refresh of the group token-status index.
 *
 * Polls the cheap aggregate `/groups/token-status` endpoint while the tab is
 * visible, pauses entirely while hidden, and refreshes immediately when the
 * tab becomes visible again. Local mutations already trigger an immediate
 * refresh through the context, so this hook only covers external changes
 * (other sessions, API-key patrols, imports) with a small footprint.
 */
export function useGroupTokenStatusPolling(intervalMs = 20000): void {
  const { refreshGroupTokenStatus } = useApp();
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    const tick = (): void => {
      if (document.visibilityState === "visible") {
        void refreshGroupTokenStatus();
      }
    };
    intervalRef.current = window.setInterval(tick, intervalMs);
    const onVisibility = (): void => {
      if (document.visibilityState === "visible") {
        tick();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current);
      }
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [refreshGroupTokenStatus, intervalMs]);
}
