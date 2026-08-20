import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../components/ui/Toast";
import { PlatformCreateModal } from "./PlatformCreateModal";

function renderModal(onCreate: (names: string[]) => Promise<void>): void {
  render(
    <ToastProvider>
      <PlatformCreateModal
        open
        existingPlatforms={[]}
        onClose={() => undefined}
        onCreate={onCreate}
      />
    </ToastProvider>,
  );
}

describe("PlatformCreateModal", () => {
  it("multi-selects presets and creates all selected platforms", async () => {
    const onCreate = vi.fn(async () => undefined);
    renderModal(onCreate);

    fireEvent.click(screen.getByRole("button", { name: /OpenAI/ }));
    fireEvent.click(screen.getByRole("button", { name: /GitHub/ }));

    expect(screen.getByText("已选 2 个")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "创建 (2)" }));

    await waitFor(() => {
      expect(onCreate).toHaveBeenCalledWith(["OpenAI", "GitHub"]);
    });
  });

  it("skips presets that already exist", () => {
    const onCreate = vi.fn(async () => undefined);
    render(
      <ToastProvider>
        <PlatformCreateModal
          open
          existingPlatforms={[{ id: 1, name: "GitHub" }]}
          onClose={() => undefined}
          onCreate={onCreate}
        />
      </ToastProvider>,
    );

    const githubButton = screen.getByRole("button", { name: /GitHub/ });
    expect(githubButton).toBeDisabled();
    expect(screen.getByText("已添加")).toBeInTheDocument();
  });
});
