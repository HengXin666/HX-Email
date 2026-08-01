import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";

import { ToastProvider } from "../components/ui/Toast";
import { TempMail } from "./TempMail";

const tempMessages = vi.fn();
const tempCodes = vi.fn();
const tempLinks = vi.fn();

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: {
    div: ({
      children,
      whileHover: _whileHover,
      whileTap: _whileTap,
      ...props
    }: React.HTMLAttributes<HTMLDivElement> & {
      whileHover?: unknown;
      whileTap?: unknown;
    }) => <div {...props}>{children}</div>,
  },
}));

vi.mock("../api/client", () => ({
  api: {
    archiveTempMail: vi.fn(),
    tempMessages: (...args: unknown[]) => tempMessages(...args),
    tempCodes: (...args: unknown[]) => tempCodes(...args),
    tempLinks: (...args: unknown[]) => tempLinks(...args),
  },
}));

vi.mock("../store/AppContext", () => ({
  useApp: () => ({
    emails: [
      {
        id: 7,
        address: "signup@example.test",
        label: "Microsoft test",
        kind: "temp",
        status: "active",
      },
    ],
    createTempMail: vi.fn(),
    refreshEmails: vi.fn(),
  }),
}));

test("renders a Microsoft security code returned by the temp-mail API", async () => {
  tempMessages.mockResolvedValue([
    {
      id: "microsoft-message",
      from_address: "account-security-noreply@accountprotection.microsoft.com",
      subject: "Microsoft 帐户安全代码",
      text: "",
      html: [
        "<div><strong>安全代码:</strong> <span>432939</span></div>",
        "<p>仅在官方网站输入此代码</p>",
        '<script>window.alert("unsafe")</script>',
      ].join(""),
    },
  ]);
  tempCodes.mockResolvedValue([{ message_id: "microsoft-message", code: "432939" }]);
  tempLinks.mockResolvedValue([]);

  render(
    <MemoryRouter>
      <ToastProvider>
        <TempMail />
      </ToastProvider>
    </MemoryRouter>,
  );

  fireEvent.click(screen.getByText("Microsoft test"));

  expect(await screen.findAllByText("432939")).toHaveLength(2);
  expect(tempCodes).toHaveBeenCalledWith(7);
  expect(screen.getByText("最新验证码")).toBeInTheDocument();
  expect(screen.getByText("仅在官方网站输入此代码")).toBeInTheDocument();
  expect(document.querySelector("script")).toBeNull();
});

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
}

function deferred<T>(): Deferred<T> {
  let resolvePromise: ((value: T) => void) | undefined;
  const promise: Promise<T> = new Promise<T>((resolve) => {
    resolvePromise = resolve;
  });
  return {
    promise,
    resolve: (value: T) => resolvePromise?.(value),
  };
}

test("does not let an older refresh response replace a newer verification code", async () => {
  vi.useFakeTimers();
  const oldMessages =
    deferred<
      Array<{ id: string; from_address: string; subject: string; text: string; html: string }>
    >();
  const oldCodes = deferred<Array<{ message_id: string; code: string }>>();
  const oldLinks = deferred<Array<{ message_id: string; url: string }>>();
  tempMessages.mockReset();
  tempCodes.mockReset();
  tempLinks.mockReset();
  tempMessages
    .mockImplementationOnce(() => oldMessages.promise)
    .mockResolvedValueOnce([
      { id: "new-message", from_address: "service.test", subject: "New", text: "999999", html: "" },
    ]);
  tempCodes
    .mockImplementationOnce(() => oldCodes.promise)
    .mockResolvedValueOnce([{ message_id: "new-message", code: "999999" }]);
  tempLinks.mockImplementationOnce(() => oldLinks.promise).mockResolvedValueOnce([]);

  render(
    <MemoryRouter>
      <ToastProvider>
        <TempMail />
      </ToastProvider>
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByText("Microsoft test"));

  await act(async () => {
    vi.advanceTimersByTime(15_000);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getAllByText("999999").length).toBeGreaterThan(0);

  await act(async () => {
    oldMessages.resolve([
      {
        id: "old-message",
        from_address: "service.test",
        subject: "Old",
        text: "123456",
        html: "",
      },
    ]);
    oldCodes.resolve([{ message_id: "old-message", code: "123456" }]);
    oldLinks.resolve([]);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getAllByText("999999").length).toBeGreaterThan(0);
  expect(screen.queryByText("123456")).not.toBeInTheDocument();
  vi.useRealTimers();
});
