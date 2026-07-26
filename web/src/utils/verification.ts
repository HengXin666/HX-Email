import type { VerificationMatch } from "../types";

/** Default total wait for a fresh verification mail to arrive. */
const FRESH_CODE_TIMEOUT_MS = 60_000;
/** Default delay between live mailbox polls while waiting. */
const FRESH_CODE_POLL_INTERVAL_MS = 5_000;

export interface FreshCodeWaitOptions {
  /** Trigger a live mailbox fetch and return matches, newest first. */
  fetchMatches: () => Promise<VerificationMatch[]>;
  /** Codes already known before this request; any other code counts as fresh. */
  baselineCodes: ReadonlySet<string>;
  /** Return true to abort the wait (unmount / superseded click). */
  isCancelled?: () => boolean;
  /**
   * Called once when the first attempt finds no fresh code, with the newest
   * already-known code (or null when the mailbox has no code at all).
   */
  onNoFreshCodeYet?: (fallbackCode: string | null) => void | Promise<void>;
  timeoutMs?: number;
  pollIntervalMs?: number;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
}

export type FreshCodeOutcome =
  | { status: "fresh"; code: string; attempts: number; seenCodes: ReadonlySet<string> }
  | {
      status: "timeout";
      fallbackCode: string | null;
      attempts: number;
      seenCodes: ReadonlySet<string>;
    }
  | { status: "cancelled"; seenCodes: ReadonlySet<string> };

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Newest code in a newest-first match list, or null when none extracted yet. */
export function firstCode(matches: VerificationMatch[]): string | null {
  for (const match of matches) {
    if (match.code) return match.code;
  }
  return null;
}

/**
 * Poll a live mailbox until a verification code OUTSIDE baselineCodes shows up.
 *
 * The user typically clicks "get code" right after requesting one, before the
 * mail has actually arrived — so a single read would only ever return stale
 * codes. This keeps re-fetching until a genuinely new code arrives, reporting
 * the newest stale code once (via onNoFreshCodeYet) so the user is never left
 * empty-handed while waiting.
 *
 * A fetch failure on the first attempt propagates (credentials/network issues
 * should surface immediately); later transient failures are tolerated and the
 * loop keeps polling until the deadline.
 */
export async function waitForFreshCode(options: FreshCodeWaitOptions): Promise<FreshCodeOutcome> {
  const timeoutMs: number = options.timeoutMs ?? FRESH_CODE_TIMEOUT_MS;
  const pollIntervalMs: number = options.pollIntervalMs ?? FRESH_CODE_POLL_INTERVAL_MS;
  const sleep = options.sleep ?? defaultSleep;
  const now = options.now ?? ((): number => Date.now());
  const isCancelled = options.isCancelled ?? ((): boolean => false);

  const deadline: number = now() + timeoutMs;
  const seenCodes = new Set<string>();
  let fallbackCode: string | null = null;
  let attempts = 0;

  for (;;) {
    if (isCancelled()) return { status: "cancelled", seenCodes };
    let matches: VerificationMatch[];
    try {
      matches = await options.fetchMatches();
    } catch (error) {
      if (attempts === 0) throw error;
      matches = [];
    }
    attempts += 1;
    for (const match of matches) {
      if (match.code) seenCodes.add(match.code);
    }
    const fresh = matches.find((match) => match.code && !options.baselineCodes.has(match.code));
    if (fresh?.code) {
      return { status: "fresh", code: fresh.code, attempts, seenCodes };
    }
    if (attempts === 1) {
      fallbackCode = firstCode(matches);
      await options.onNoFreshCodeYet?.(fallbackCode);
    }
    if (isCancelled()) return { status: "cancelled", seenCodes };
    if (now() >= deadline) break;
    await sleep(pollIntervalMs);
  }
  return { status: "timeout", fallbackCode, attempts, seenCodes };
}
