import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { BasicSettingsTab } from "./BasicSettingsTab";

const mocks = vi.hoisted(() => ({
  getVersionCheck: vi.fn(),
  getDeploymentInfo: vi.fn(),
  getUpdateAnnouncement: vi.fn(),
  getUpdateStatus: vi.fn(),
  applyUpdate: vi.fn(),
  updateCredentials: vi.fn(),
}));

vi.mock("../../../api/client", () => ({
  api: {
    getVersionCheck: mocks.getVersionCheck,
    getDeploymentInfo: mocks.getDeploymentInfo,
    getUpdateAnnouncement: mocks.getUpdateAnnouncement,
    getUpdateStatus: mocks.getUpdateStatus,
    applyUpdate: mocks.applyUpdate,
  },
}));

vi.mock("../../../store/AppContext", () => ({
  useApp: () => ({ updateCredentials: mocks.updateCredentials }),
}));

const versionCheck = {
  success: true,
  source: "github_release",
  version: "0.2.0",
  current_version: "0.2.0",
  latest_version: "1.5.0",
  has_update: true,
  up_to_date: false,
  title: "新增流水线与自动更新",
  body: "更新内容",
  html_url: "https://github.com/HengXin666/HX-Email/releases/tag/v1.5.0",
  published_at: "2026-08-11T00:00:00Z",
  repository_url: "https://github.com/HengXin666/HX-Email",
};

const idleStatus = {
  enabled: true,
  available: true,
  available_reason: "",
  running: false,
  phase: "",
  success: null,
  message: "",
  output: "",
  target_version: "",
  started_at: "",
  finished_at: "",
  last_update: {},
};

const renderTab = (): void => {
  render(
    <BasicSettingsTab
      settings={{}}
      setSetting={vi.fn()}
      toast={vi.fn()}
      user={null}
      accounts={[]}
    />,
  );
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getVersionCheck.mockResolvedValue(versionCheck);
  mocks.getDeploymentInfo.mockResolvedValue({
    python_version: "3.12.0",
    platform: "Linux",
  });
  mocks.getUpdateAnnouncement.mockResolvedValue(versionCheck);
  mocks.getUpdateStatus.mockResolvedValue(idleStatus);
});

test("shows the update banner and applies the update after confirmation", async () => {
  mocks.applyUpdate.mockResolvedValue({ ...idleStatus, running: true, phase: "启动更新容器" });
  renderTab();

  expect(await screen.findByText("发现新版本 v1.5.0")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /立即更新/ }));

  expect(await screen.findByText(/更新到 v1\.5\.0/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /确认更新/ }));

  await waitFor(() => expect(mocks.applyUpdate).toHaveBeenCalledWith("1.5.0"));
});

test("hides the update banner when already up to date", async () => {
  mocks.getVersionCheck.mockResolvedValue({
    ...versionCheck,
    latest_version: "0.2.0",
    has_update: false,
    up_to_date: true,
  });
  renderTab();

  expect(await screen.findByText("已是最新")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /立即更新/ })).not.toBeInTheDocument();
});

test("shows a hint when self-update is not available", async () => {
  mocks.getUpdateStatus.mockResolvedValue({
    ...idleStatus,
    available: false,
    available_reason: "自动更新未启用, 请先配置",
  });
  renderTab();

  expect(await screen.findByText("自动更新未启用, 请先配置")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /立即更新/ })).not.toBeInTheDocument();
});
