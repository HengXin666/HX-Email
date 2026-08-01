import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { LatestMailMessage } from "../../types";
import { OverviewLatestMail } from "./OverviewLatestMail";

const message: LatestMailMessage = {
  id: 9,
  usable_email_id: 4,
  address: "owner@example.com",
  group: { id: 2, name: "注册", color: "#58a6ff" },
  from_address: "security@example.com",
  recipient_address: "owner@example.com",
  subject: "Your verification code",
  body: "Use 482913 to continue.",
  verification_code: "482913",
  received_at: "2026-08-01T10:00:00Z",
};

test("latest mail list renders cross-mailbox context and selects its usable email", () => {
  const onSelectEmail = vi.fn();
  render(
    <OverviewLatestMail
      messages={[message]}
      selectedEmailId={null}
      onSelectEmail={onSelectEmail}
    />,
  );

  expect(screen.getByText("Your verification code")).toBeInTheDocument();
  expect(screen.getByText("482913")).toBeInTheDocument();
  expect(screen.getByText("owner@example.com")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button"));
  expect(onSelectEmail).toHaveBeenCalledWith(4);
});
