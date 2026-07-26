import { expect, test, vi } from "vitest";

import type { VerificationMatch } from "../types";
import { firstCode, waitForFreshCode } from "./verification";

function match(code: string | null): VerificationMatch {
  return { code, link: null, recipient_address: null, certainty: "certain", subject: "" };
}

interface FakeClock {
  now: () => number;
  sleep: (ms: number) => Promise<void>;
}

function makeClock(): FakeClock {
  let elapsed = 0;
  return {
    now: () => elapsed,
    sleep: (ms: number) => {
      elapsed += ms;
      return Promise.resolve();
    },
  };
}

test("firstCode returns the newest non-empty code", () => {
  expect(firstCode([match(null), match("111111"), match("222222")])).toBe("111111");
  expect(firstCode([match(null)])).toBeNull();
  expect(firstCode([])).toBeNull();
});

test("fresh code already arrived is returned on the first attempt", async () => {
  const clock = makeClock();
  const onNoFreshCodeYet = vi.fn();

  const outcome = await waitForFreshCode({
    fetchMatches: () => Promise.resolve([match("999999"), match("123456")]),
    baselineCodes: new Set(["123456"]),
    onNoFreshCodeYet,
    ...clock,
  });

  expect(outcome).toMatchObject({ status: "fresh", code: "999999", attempts: 1 });
  expect(onNoFreshCodeYet).not.toHaveBeenCalled();
});

test("waits through polls until a new code arrives, reporting stale fallback once", async () => {
  const clock = makeClock();
  const onNoFreshCodeYet = vi.fn();
  let calls = 0;
  const fetchMatches = (): Promise<VerificationMatch[]> => {
    calls += 1;
    return Promise.resolve(calls >= 3 ? [match("777777"), match("123456")] : [match("123456")]);
  };

  const outcome = await waitForFreshCode({
    fetchMatches,
    baselineCodes: new Set(["123456"]),
    onNoFreshCodeYet,
    timeoutMs: 60_000,
    pollIntervalMs: 5_000,
    ...clock,
  });

  expect(outcome).toMatchObject({ status: "fresh", code: "777777", attempts: 3 });
  expect(onNoFreshCodeYet).toHaveBeenCalledTimes(1);
  expect(onNoFreshCodeYet).toHaveBeenCalledWith("123456");
});

test("times out with the stale fallback code and reports every code seen", async () => {
  const clock = makeClock();

  const outcome = await waitForFreshCode({
    fetchMatches: () => Promise.resolve([match("123456"), match("654321")]),
    baselineCodes: new Set(["123456", "654321"]),
    timeoutMs: 10_000,
    pollIntervalMs: 5_000,
    ...clock,
  });

  expect(outcome).toMatchObject({ status: "timeout", fallbackCode: "123456", attempts: 3 });
  expect([...outcome.seenCodes].sort()).toEqual(["123456", "654321"]);
});

test("times out with null fallback when the mailbox has no code at all", async () => {
  const clock = makeClock();
  const onNoFreshCodeYet = vi.fn();

  const outcome = await waitForFreshCode({
    fetchMatches: () => Promise.resolve([]),
    baselineCodes: new Set(),
    onNoFreshCodeYet,
    timeoutMs: 5_000,
    pollIntervalMs: 5_000,
    ...clock,
  });

  expect(outcome).toMatchObject({ status: "timeout", fallbackCode: null });
  expect(onNoFreshCodeYet).toHaveBeenCalledTimes(1);
  expect(onNoFreshCodeYet).toHaveBeenCalledWith(null);
});

test("cancellation stops the wait between polls", async () => {
  const clock = makeClock();
  let calls = 0;

  const outcome = await waitForFreshCode({
    fetchMatches: () => {
      calls += 1;
      return Promise.resolve([match("123456")]);
    },
    baselineCodes: new Set(["123456"]),
    isCancelled: () => calls >= 2,
    timeoutMs: 60_000,
    pollIntervalMs: 5_000,
    ...clock,
  });

  expect(outcome.status).toBe("cancelled");
  expect(calls).toBe(2);
});

test("a failing first fetch propagates to the caller", async () => {
  await expect(
    waitForFreshCode({
      fetchMatches: () => Promise.reject(new Error("IMAP down")),
      baselineCodes: new Set(),
      ...makeClock(),
    }),
  ).rejects.toThrow("IMAP down");
});

test("transient fetch failures after the first attempt keep the wait alive", async () => {
  const clock = makeClock();
  let calls = 0;
  const fetchMatches = (): Promise<VerificationMatch[]> => {
    calls += 1;
    if (calls === 2) return Promise.reject(new Error("transient"));
    return Promise.resolve(calls >= 3 ? [match("777777")] : [match("123456")]);
  };

  const outcome = await waitForFreshCode({
    fetchMatches,
    baselineCodes: new Set(["123456"]),
    timeoutMs: 60_000,
    pollIntervalMs: 5_000,
    ...clock,
  });

  expect(outcome).toMatchObject({ status: "fresh", code: "777777", attempts: 3 });
});
