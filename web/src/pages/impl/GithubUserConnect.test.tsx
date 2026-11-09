import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import { ToastProvider } from "../../components/ui/Toast";
import type {
  GithubUserCheckResult,
  MessagingInstance,
  RouterActionSpec,
} from "../../types/messaging";
import { GithubUserConnect } from "./GithubUserConnect";

function account(config: Record<string, string> = {}): MessagingInstance {
  return {
    id: 9,
    kind: "github_user",
    name: "GitHub 账号",
    status: "online",
    config: { cli: "/home/me/.local/bin/gh-agent", repository: "hx/HX-Email", ...config },
    created_at: "",
    updated_at: "",
  };
}

const ACTIONS: RouterActionSpec[] = [
  { name: "message_send", targets: ["issue"], requires: ["repo"], description: "", params: [] },
  { name: "reaction_add", targets: ["issue"], requires: ["repo"], description: "", params: [] },
];

function result(ok: boolean, extra: Partial<GithubUserCheckResult["report"]> = {}) {
  return {
    instance: account(ok ? { login: "hx-agent" } : {}),
    report: {
      ok,
      code: ok ? "ok" : "not_authenticated",
      message: ok ? "已读到账号 hx-agent" : "没有登录 GitHub",
      hint: ok ? "" : "在终端运行 /home/me/.local/bin/gh-agent auth login",
      login: ok ? "hx-agent" : "",
      scopes: [],
      missing_scopes: [],
      ...extra,
    },
  };
}

function renderCard(): void {
  render(
    <ToastProvider>
      <GithubUserConnect />
    </ToastProvider>,
  );
}

describe("GithubUserConnect", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("asks only for the CLI path and repository, never a token", async () => {
    vi.spyOn(api, "listInstances").mockResolvedValue([]);
    renderCard();
    expect(await screen.findByText("GitHub 账号 (gh CLI)")).toBeTruthy();
    expect(screen.getByLabelText("CLI 路径")).toBeTruthy();
    expect(screen.getByLabelText("仓库 (owner/name)")).toBeTruthy();
    expect(screen.queryByLabelText(/token/i)).toBeNull();
    expect(screen.getByText(/auth login/)).toBeTruthy();
    expect(screen.getByText(/GH_CONFIG_DIR/)).toBeTruthy();
  });

  it("saves, checks and shows the login read by the CLI", async () => {
    vi.spyOn(api, "listInstances").mockResolvedValue([]);
    vi.spyOn(api, "githubActions").mockResolvedValue(ACTIONS);
    const save = vi.spyOn(api, "githubUserSave").mockResolvedValue(result(true));
    renderCard();
    fireEvent.change(await screen.findByLabelText("CLI 路径"), {
      target: { value: "/home/me/.local/bin/gh-agent" },
    });
    fireEvent.change(screen.getByLabelText("仓库 (owner/name)"), {
      target: { value: "hx/HX-Email" },
    });
    fireEvent.click(screen.getByText("检查"));
    expect(await screen.findByText("hx-agent")).toBeTruthy();
    expect(save).toHaveBeenCalledWith({
      cli: "/home/me/.local/bin/gh-agent",
      repository: "hx/HX-Email",
    });
    await waitFor(() => expect(api.githubActions).toHaveBeenCalledWith("github_user"));
    expect(await screen.findByText("reaction_add")).toBeTruthy();
  });

  it("shows the failure code and hint", async () => {
    vi.spyOn(api, "listInstances").mockResolvedValue([account()]);
    vi.spyOn(api, "githubActions").mockResolvedValue(ACTIONS);
    const save = vi.spyOn(api, "githubUserSave").mockResolvedValue(result(false));
    renderCard();
    await waitFor(() =>
      expect((screen.getByLabelText("CLI 路径") as HTMLInputElement).value).toBe(
        "/home/me/.local/bin/gh-agent",
      ),
    );
    fireEvent.click(screen.getByText("检查"));
    expect(await screen.findByText("not_authenticated")).toBeTruthy();
    expect(screen.getByText(/^在终端运行 .*auth login$/)).toBeTruthy();
    expect(save.mock.calls[0][0]).toMatchObject({ instance_id: 9 });
  });

  it("writes observe switches into the instance config", async () => {
    vi.spyOn(api, "listInstances").mockResolvedValue([account()]);
    vi.spyOn(api, "githubActions").mockResolvedValue(ACTIONS);
    const update = vi
      .spyOn(api, "updateConfig")
      .mockResolvedValue(account({ observe_comments: "1" }));
    renderCard();
    fireEvent.click(await screen.findByText("全部评论"));
    await waitFor(() => expect(update).toHaveBeenCalledWith(9, { observe_comments: "1" }));
  });
});
