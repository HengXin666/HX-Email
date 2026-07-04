import { expect, test } from "vitest";

import { parseDateTime } from "./time";

test("parses database timestamps as local wall time", () => {
  const parsed = parseDateTime("2026-07-04 16:05:06");

  expect(parsed?.getFullYear()).toBe(2026);
  expect(parsed?.getMonth()).toBe(6);
  expect(parsed?.getDate()).toBe(4);
  expect(parsed?.getHours()).toBe(16);
  expect(parsed?.getMinutes()).toBe(5);
  expect(parsed?.getSeconds()).toBe(6);
});

test("preserves explicit timezone offsets", () => {
  const parsed = parseDateTime("2026-07-04T08:05:06Z");

  expect(parsed?.toISOString()).toBe("2026-07-04T08:05:06.000Z");
});
