import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { GoogleVerificationCard } from "./GoogleVerificationCard";

const mocks = vi.hoisted(() => ({
  listGoogleVerificationFiles: vi.fn(),
  uploadGoogleVerificationFile: vi.fn(),
  deleteGoogleVerificationFile: vi.fn(),
}));

vi.mock("../../../api/client", () => ({
  api: {
    listGoogleVerificationFiles: mocks.listGoogleVerificationFiles,
    uploadGoogleVerificationFile: mocks.uploadGoogleVerificationFile,
    deleteGoogleVerificationFile: mocks.deleteGoogleVerificationFile,
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { origin: "https://email.woa.qzz.io" },
  });
});

test("shows the uploaded verification file with its public URL", async () => {
  const toast = vi.fn();
  mocks.listGoogleVerificationFiles.mockResolvedValue({
    files: [{ filename: "google18261d952ce2f02c.html", url: "/google18261d952ce2f02c.html" }],
  });
  render(<GoogleVerificationCard toast={toast} />);

  expect(await screen.findByText("google18261d952ce2f02c.html")).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "https://email.woa.qzz.io/google18261d952ce2f02c.html" }),
  ).toBeInTheDocument();
});

test("uploads a selected verification file and refreshes the list", async () => {
  const toast = vi.fn();
  mocks.listGoogleVerificationFiles.mockResolvedValueOnce({ files: [] });
  const verificationFile: File = new File(
    ["google-site-verification: google18261d952ce2f02c.html"],
    "google18261d952ce2f02c.html",
    { type: "text/html" },
  );
  mocks.uploadGoogleVerificationFile.mockResolvedValue({
    filename: "google18261d952ce2f02c.html",
    url: "/google18261d952ce2f02c.html",
  });
  mocks.listGoogleVerificationFiles.mockResolvedValueOnce({
    files: [{ filename: "google18261d952ce2f02c.html", url: "/google18261d952ce2f02c.html" }],
  });
  render(<GoogleVerificationCard toast={toast} />);

  await screen.findByText("尚未上传验证文件");

  fireEvent.change(screen.getByLabelText("选择 Google 站点验证 HTML 文件"), {
    target: { files: [verificationFile] },
  });
  fireEvent.click(screen.getByRole("button", { name: "上传" }));

  await waitFor(() =>
    expect(mocks.uploadGoogleVerificationFile).toHaveBeenCalledWith(verificationFile),
  );
  expect(await screen.findByText("google18261d952ce2f02c.html")).toBeInTheDocument();
  expect(toast).toHaveBeenCalledWith(
    "验证文件已上传：https://email.woa.qzz.io/google18261d952ce2f02c.html",
    "success",
  );
});

test("deletes the verification file after confirmation", async () => {
  const toast = vi.fn();
  mocks.listGoogleVerificationFiles.mockResolvedValueOnce({
    files: [{ filename: "google18261d952ce2f02c.html", url: "/google18261d952ce2f02c.html" }],
  });
  mocks.deleteGoogleVerificationFile.mockResolvedValue(null);
  mocks.listGoogleVerificationFiles.mockResolvedValue({ files: [] });
  render(<GoogleVerificationCard toast={toast} />);

  fireEvent.click(await screen.findByRole("button", { name: "删除" }));
  fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

  await waitFor(() =>
    expect(mocks.deleteGoogleVerificationFile).toHaveBeenCalledWith("google18261d952ce2f02c.html"),
  );
  expect(await screen.findByText("尚未上传验证文件")).toBeInTheDocument();
});
