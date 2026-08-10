import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { SyncSettingsTab } from "./SyncSettingsTab";

const mocks = vi.hoisted(() => ({
  getSyncStatus: vi.fn(),
  runSyncNow: vi.fn(),
}));

vi.mock("../../../api/client", () => ({
  api: {
    getSyncStatus: mocks.getSyncStatus,
    runSyncNow: mocks.runSyncNow,
  },
}));

const enabledStatus = {
  running: false,
  enabled: true,
  interval_seconds: 300,
  last_run: "2026-08-11T00:00:00Z",
  next_run: "2026-08-11T00:05:00Z",
  last_error: "",
  last_summary: {},
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getSyncStatus.mockResolvedValue(enabledStatus);
});

test("shows sync configuration inputs and live status", async () => {
  const setSetting = vi.fn();
  render(
    <SyncSettingsTab
      settings={{
        sync_url: "http://vps.example.com:8080",
        sync_token: "tok",
        sync_interval_seconds: "300",
      }}
      setSetting={setSetting}
      toast={vi.fn()}
      user={null}
      accounts={[]}
    />,
  );

  expect(await screen.findByText("已启用")).toBeInTheDocument();
  expect(screen.getByLabelText("主实例地址")).toHaveValue("http://vps.example.com:8080");
  expect(screen.getByLabelText("同步 Token")).toHaveValue("tok");
  expect(screen.getByLabelText("同步间隔 (秒)")).toHaveValue(300);
  expect(screen.getByText("2026-08-11T00:00:00Z")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("主实例地址"), {
    target: { value: "http://other.example.com:8080" },
  });
  expect(setSetting).toHaveBeenCalledWith("sync_url", "http://other.example.com:8080");
});

test("runs a sync round on demand and toasts success", async () => {
  const toast = vi.fn();
  mocks.runSyncNow.mockResolvedValue({
    started_at: "2026-08-11T00:01:00Z",
    finished_at: "2026-08-11T00:01:02Z",
    error: "",
    tables: { mail_meta: 12 },
    files: {},
    push: {},
  });
  render(
    <SyncSettingsTab
      settings={{ sync_url: "http://vps.example.com:8080", sync_token: "tok" }}
      setSetting={vi.fn()}
      toast={toast}
      user={null}
      accounts={[]}
    />,
  );

  fireEvent.click(await screen.findByRole("button", { name: /立即同步/ }));

  await waitFor(() => expect(mocks.runSyncNow).toHaveBeenCalledOnce());
  expect(toast).toHaveBeenCalledWith("同步完成", "success");
});

test("toasts the backend error when a sync round fails", async () => {
  const toast = vi.fn();
  mocks.runSyncNow.mockResolvedValue({
    started_at: "2026-08-11T00:01:00Z",
    finished_at: "2026-08-11T00:01:02Z",
    error: "主实例不可达",
    tables: {},
    files: {},
    push: {},
  });
  render(
    <SyncSettingsTab
      settings={{ sync_url: "http://vps.example.com:8080", sync_token: "tok" }}
      setSetting={vi.fn()}
      toast={toast}
      user={null}
      accounts={[]}
    />,
  );

  fireEvent.click(await screen.findByRole("button", { name: /立即同步/ }));

  await waitFor(() => expect(mocks.runSyncNow).toHaveBeenCalledOnce());
  expect(toast).toHaveBeenCalledWith("同步出错：主实例不可达", "error");
});

test("shows the last sync error when one is present", async () => {
  mocks.getSyncStatus.mockResolvedValue({
    ...enabledStatus,
    last_error: "push failed: 401 Unauthorized",
  });
  render(
    <SyncSettingsTab
      settings={{}}
      setSetting={vi.fn()}
      toast={vi.fn()}
      user={null}
      accounts={[]}
    />,
  );

  expect(await screen.findByText("push failed: 401 Unauthorized")).toBeInTheDocument();
});
