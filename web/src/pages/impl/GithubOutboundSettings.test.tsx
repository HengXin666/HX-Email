import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import { ToastProvider } from "../../components/ui/Toast";
import type { MessagingInstance, RouterActionSpec } from "../../types/messaging";
import { GithubOutboundSettings, parseDisabled, serializeDisabled } from "./GithubOutboundSettings";

function spec(name: string, requires: string[]): RouterActionSpec {
  return { name, targets: ["issue"], requires, description: name, params: [] };
}

const ACTIONS: RouterActionSpec[] = [
  spec("message_send", []),
  spec("reaction_add", ["issues:write"]),
  spec("review_submit", ["pull_requests:write"]),
  spec("discussion_create", ["discussions:write"]),
];

function instance(config: Record<string, string>): MessagingInstance {
  return {
    id: 7,
    kind: "github",
    name: "GitHub",
    status: "idle",
    config,
    created_at: "",
    updated_at: "",
  };
}

function renderSettings(config: Record<string, string>): void {
  render(
    <ToastProvider>
      <GithubOutboundSettings instance={instance(config)} />
    </ToastProvider>,
  );
}

describe("GithubOutboundSettings", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("parses and serializes the disabled list", () => {
    expect([...parseDisabled(" review_submit, ,reaction_add ")]).toEqual([
      "review_submit",
      "reaction_add",
    ]);
    expect(parseDisabled(undefined).size).toBe(0);
    expect(serializeDisabled(new Set(["review_submit", "reaction_add"]))).toBe(
      "reaction_add,review_submit",
    );
  });

  it("lists every declared action except message_send, all on by default", async () => {
    vi.spyOn(api, "githubActions").mockResolvedValue(ACTIONS);
    renderSettings({});
    const review = await screen.findByRole("checkbox", { name: "review_submit" });
    expect(review).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "discussion_create" })).toBeChecked();
    expect(screen.queryByRole("checkbox", { name: "message_send" })).not.toBeInTheDocument();
    expect(screen.getByText("discussions:write")).toBeInTheDocument();
  });

  it("turns an action off and back on through the instance config", async () => {
    vi.spyOn(api, "githubActions").mockResolvedValue(ACTIONS);
    const update = vi
      .spyOn(api, "updateConfig")
      .mockResolvedValueOnce(instance({ disabled_actions: "reaction_add,review_submit" }))
      .mockResolvedValueOnce(instance({ disabled_actions: "reaction_add" }));
    renderSettings({ disabled_actions: "reaction_add" });

    const reaction = await screen.findByRole("checkbox", { name: "reaction_add" });
    expect(reaction).not.toBeChecked();
    fireEvent.click(screen.getByRole("checkbox", { name: "review_submit" }));
    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(7, { disabled_actions: "reaction_add,review_submit" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: "review_submit" })).not.toBeChecked(),
    );
    expect(await screen.findByText(/review_submit 已关闭/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: "review_submit" }));
    await waitFor(() =>
      expect(update).toHaveBeenLastCalledWith(7, { disabled_actions: "reaction_add" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: "review_submit" })).toBeChecked(),
    );
  });

  it("keeps the old state when saving fails", async () => {
    vi.spyOn(api, "githubActions").mockResolvedValue(ACTIONS);
    vi.spyOn(api, "updateConfig").mockRejectedValue(new Error("保存失败了"));
    renderSettings({});
    fireEvent.click(await screen.findByRole("checkbox", { name: "reaction_add" }));
    expect(await screen.findByText("保存失败了")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "reaction_add" })).toBeChecked();
  });
});
