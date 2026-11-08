import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import { ToastProvider } from "../../components/ui/Toast";
import type { GithubVerifyResult, MessagingInstance } from "../../types/messaging";
import { describeGithubError, GithubAppConnect } from "./GithubAppConnect";

const githubInstance: MessagingInstance = {
  id: 7,
  kind: "github",
  name: "GitHub",
  status: "idle",
  config: {},
  created_at: "",
  updated_at: "",
};

const verifiedResult: GithubVerifyResult = {
  verified: true,
  app: "hx-router",
  installations: [{ id: 42, account: "octo-org" }],
  app_config: {
    app_id: 1,
    app_slug: "hx-router",
    client_id: "Iv1.x",
    has_private_key: true,
    has_webhook_secret: false,
  },
};

function renderCard(): void {
  render(
    <ToastProvider>
      <GithubAppConnect />
    </ToastProvider>,
  );
}

describe("GithubAppConnect", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/messaging");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("maps callback reasons to readable text", () => {
    expect(describeGithubError("invalid_state")).toContain("过期");
    expect(describeGithubError("weird")).toContain("weird");
  });

  it("shows the one-click button when no GitHub instance exists", async () => {
    vi.spyOn(api, "listInstances").mockResolvedValue([]);
    renderCard();
    expect(await screen.findByRole("button", { name: /用 GitHub 一键创建/ })).toBeInTheDocument();
  });

  it("shows the error toast from the callback and clears the query", async () => {
    window.history.replaceState(null, "", "/messaging?error=save_failed");
    vi.spyOn(api, "listInstances").mockResolvedValue([]);
    renderCard();
    expect(await screen.findByText(/保存到本服务失败/)).toBeInTheDocument();
    expect(window.location.search).toBe("");
  });

  it("verifies on load and attaches an installation", async () => {
    vi.spyOn(api, "listInstances").mockResolvedValue([githubInstance]);
    vi.spyOn(api, "githubVerify").mockResolvedValue(verifiedResult);
    vi.spyOn(api, "githubActions").mockResolvedValue([
      {
        name: "review_submit",
        targets: ["issue"],
        requires: ["pull_requests:write"],
        description: "",
        params: [],
      },
    ]);
    const attach = vi
      .spyOn(api, "githubAttach")
      .mockResolvedValue({ attached: true, installation: { id: 42, account: "octo-org" } });
    renderCard();

    expect(await screen.findByText("octo-org")).toBeInTheDocument();
    expect(screen.getByText("未配置")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /绑定到这个实例/ }));
    await waitFor(() => expect(attach).toHaveBeenCalledWith(42, 7));
    expect(await screen.findByText(/已绑定 octo-org/)).toBeInTheDocument();
    expect(await screen.findByRole("checkbox", { name: "review_submit" })).toBeChecked();
  });
});
