import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ToastProvider } from "../components/ui/Toast";
import type { Platform, PlatformBinding, UsableEmail } from "../types";
import { Platforms } from "./Platforms";

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: {
    div: ({
      children,
      animate: _animate,
      exit: _exit,
      initial: _initial,
      transition: _transition,
      whileHover: _whileHover,
      whileTap: _whileTap,
      ...props
    }: React.HTMLAttributes<HTMLDivElement> & Record<string, unknown>) => (
      <div {...props}>{children}</div>
    ),
  },
}));

const listBindings = vi.fn();
const createBinding = vi.fn();
const createEmail = vi.fn();
const refreshEmails = vi.fn();
const refreshPlatforms = vi.fn();

const platforms: Platform[] = [
  { id: 1, name: "GitHub", binding_count: 1 },
  { id: 2, name: "Stripe", binding_count: 1 },
];

const emails: UsableEmail[] = [
  {
    id: 10,
    address: "one@example.com",
    label: "One",
    kind: "custom",
    status: "active",
    platform_binding_count: 1,
  },
  {
    id: 11,
    address: "two@example.com",
    label: "Two",
    kind: "custom",
    status: "active",
    platform_binding_count: 1,
  },
];

const githubBinding: PlatformBinding = {
  id: 100,
  usable_email_id: 10,
  platform: platforms[0],
  status: "active",
  notes: "",
};

const stripeBinding: PlatformBinding = {
  id: 101,
  usable_email_id: 11,
  platform: platforms[1],
  status: "active",
  notes: "",
};

vi.mock("../api/client", () => ({
  api: {
    listBindings: (...args: unknown[]) => listBindings(...args),
    createBinding: (...args: unknown[]) => createBinding(...args),
  },
}));

vi.mock("../store/AppContext", () => ({
  useApp: () => ({
    platforms,
    emails,
    createPlatform: vi.fn(),
    updatePlatform: vi.fn(),
    deletePlatform: vi.fn(),
    createEmail,
    refreshEmails,
    refreshPlatforms,
  }),
}));

function renderPlatforms(): void {
  render(
    <ToastProvider>
      <Platforms />
    </ToastProvider>,
  );
}

beforeEach(() => {
  listBindings.mockImplementation((emailId: number) => {
    if (emailId === 10) return Promise.resolve([githubBinding]);
    if (emailId === 11) return Promise.resolve([stripeBinding]);
    return Promise.resolve([]);
  });
  createBinding.mockResolvedValue({
    id: 102,
    usable_email_id: 12,
    platform: platforms[0],
    status: "active",
    notes: "",
  });
  createEmail.mockResolvedValue({
    id: 12,
    address: "owner+github@example.com",
    label: "GitHub alias",
    kind: "custom",
    status: "active",
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

test("platform detail only lists emails bound to the selected platform", async () => {
  renderPlatforms();

  fireEvent.click(screen.getByText("GitHub"));

  await screen.findByText("one@example.com");
  expect(screen.queryByText("two@example.com")).not.toBeInTheDocument();
});

test("platform page can create a standalone plus email and bind it", async () => {
  renderPlatforms();
  fireEvent.click(screen.getByText("GitHub"));

  fireEvent.click(await screen.findByRole("button", { name: "添加邮箱" }));
  fireEvent.change(screen.getByLabelText("新邮箱地址"), {
    target: { value: "owner+github@example.com" },
  });
  fireEvent.change(screen.getByLabelText("备注名称"), {
    target: { value: "GitHub alias" },
  });
  fireEvent.click(screen.getByRole("button", { name: "添加" }));

  await waitFor(() => {
    expect(createEmail).toHaveBeenCalledWith("owner+github@example.com", "GitHub alias");
  });
  expect(createBinding).toHaveBeenCalledWith(12, 1, "active", "");
  expect(refreshEmails).toHaveBeenCalled();
  expect(refreshPlatforms).toHaveBeenCalled();
  expect(await screen.findByText("owner+github@example.com")).toBeInTheDocument();
});
