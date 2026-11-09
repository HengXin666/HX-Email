import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import { ToastProvider } from "../../components/ui/Toast";
import { DEFAULT_SCOPES, KeyScopeEditor, ScopePicker } from "./RouterKeyScopes";
import { SubscriptionIntegration } from "./SubscriptionIntegration";

function Harness({ initial }: { initial: string[] }) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <ScopePicker value={value} onChange={setValue} idPrefix="t" />
      <output data-testid="value">{value.join(" ")}</output>
    </>
  );
}

describe("router key scopes", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("defaults to every scope except admin, like keys issued before scopes", () => {
    expect(DEFAULT_SCOPES).toContain("router:send");
    expect(DEFAULT_SCOPES).toContain("mcp");
    expect(DEFAULT_SCOPES).not.toContain("admin");
  });

  it("toggles scopes and keeps the canonical order", () => {
    render(<Harness initial={["mcp"]} />);
    fireEvent.click(screen.getByLabelText(/router:read/));
    fireEvent.click(screen.getByLabelText(/^admin/));
    expect(screen.getByTestId("value").textContent).toBe("router:read mcp admin");
    fireEvent.click(screen.getByLabelText(/^mcp/));
    expect(screen.getByTestId("value").textContent).toBe("router:read admin");
  });

  it("edits an existing key and refuses an empty scope set", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<KeyScopeEditor keyId={3} scopes={["router:read"]} onSave={onSave} />);
    expect(screen.getByTestId("scopes-3").textContent).toBe("router:read");
    fireEvent.click(screen.getByText("改权限"));
    fireEvent.click(screen.getByLabelText(/router:read/));
    expect(screen.getByText("保存权限").closest("button")).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/router:send/));
    fireEvent.click(screen.getByText("保存权限"));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(3, ["router:send"]));
  });

  it("creates a key with the chosen scopes and patches scopes of a listed key", async () => {
    vi.spyOn(api, "listRouterKeys").mockResolvedValue({
      keys: [
        {
          id: 5,
          name: "bot",
          key_prefix: "hxr_abcd",
          created_at: "",
          scopes: ["router:read", "mcp"],
        },
      ],
    });
    const create = vi.spyOn(api, "createRouterKey").mockResolvedValue({
      id: 6,
      name: "agent",
      key_prefix: "hxr_efgh",
      created_at: "",
      key: "hxr_secret",
      scopes: ["router:read"],
    });
    const patch = vi
      .spyOn(api, "updateRouterKeyScopes")
      .mockResolvedValue({ id: 5, scopes: ["router:read"] });
    render(
      <ToastProvider>
        <SubscriptionIntegration selected={null} />
      </ToastProvider>,
    );
    expect(await screen.findByTestId("scopes-5")).toHaveTextContent("router:read mcp");
    for (const scope of DEFAULT_SCOPES.filter((item) => item !== "router:read")) {
      fireEvent.click(screen.getByLabelText(new RegExp(`^${scope}`)));
    }
    fireEvent.click(screen.getByText("新建路由密钥"));
    await waitFor(() => expect(create).toHaveBeenCalledWith("agent", ["router:read"]));
    fireEvent.click(screen.getByText("改权限"));
    fireEvent.click(screen.getByLabelText(/key-5|^mcp/, { selector: "#key-5-mcp" }));
    fireEvent.click(screen.getByText("保存权限"));
    await waitFor(() => expect(patch).toHaveBeenCalledWith(5, ["router:read"]));
  });
});
