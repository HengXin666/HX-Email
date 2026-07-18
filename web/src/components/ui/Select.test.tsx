import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { expect, test, vi } from "vitest";
import { Select } from "./Primitives";

test("select uses the Radix combobox instead of a native select", async () => {
  const onChange = vi.fn();
  const { container } = render(
    <Select
      label="服务商"
      value="microsoft"
      onChange={onChange}
      options={[
        { value: "microsoft", label: "Microsoft Outlook" },
        { value: "google", label: "Google Gmail" },
      ]}
    />,
  );

  expect(container.querySelector("select")).toBeNull();
  fireEvent.click(screen.getByRole("combobox", { name: "服务商" }));
  fireEvent.keyDown(await screen.findByRole("option", { name: "Google Gmail" }), { key: "Enter" });
  expect(onChange).toHaveBeenCalledWith("google");
});
