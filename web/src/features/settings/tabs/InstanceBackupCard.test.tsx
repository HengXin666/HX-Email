import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { InstanceBackupCard } from "./InstanceBackupCard";

const mocks = vi.hoisted(() => ({
  exportInstanceBackup: vi.fn(),
  importInstanceBackup: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("../../../api/client", () => ({
  api: {
    exportInstanceBackup: mocks.exportInstanceBackup,
    importInstanceBackup: mocks.importInstanceBackup,
  },
}));

vi.mock("../../../store/AppContext", () => ({
  useApp: () => ({ logout: mocks.logout }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.logout.mockResolvedValue(undefined);
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn(() => "blob:backup"),
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: vi.fn(),
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
});

test("downloads a complete instance backup", async () => {
  const toast = vi.fn();
  mocks.exportInstanceBackup.mockResolvedValue(new Blob(["backup"], { type: "application/zip" }));
  render(<InstanceBackupCard toast={toast} />);

  fireEvent.click(screen.getByRole("button", { name: "导出完整实例" }));

  await waitFor(() => expect(mocks.exportInstanceBackup).toHaveBeenCalledOnce());
  expect(toast).toHaveBeenCalledWith("实例备份已下载", "success");
});

test("confirms and imports a selected backup before logging out", async () => {
  const toast = vi.fn();
  const backupFile: File = new File(["backup"], "restore.zip", { type: "application/zip" });
  mocks.importInstanceBackup.mockResolvedValue({ restored: true, requires_relogin: true });
  render(<InstanceBackupCard toast={toast} />);

  fireEvent.change(screen.getByLabelText("选择实例备份 ZIP"), {
    target: { files: [backupFile] },
  });
  fireEvent.click(screen.getByRole("button", { name: "恢复并重新登录" }));

  await waitFor(() => expect(mocks.importInstanceBackup).toHaveBeenCalledWith(backupFile));
  await waitFor(() => expect(mocks.logout).toHaveBeenCalledOnce());
  expect(toast).toHaveBeenCalledWith("实例已恢复，请使用备份中的管理员重新登录", "success");
});
