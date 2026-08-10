import { test } from "@playwright/test";

test("footer screenshots", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("http://127.0.0.1:14173/login");
  await page.waitForTimeout(1500);
  await page.screenshot({ path: "/tmp/footer-login.png" });
  await page.getByRole("button", { name: "去注册" }).click();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: "/tmp/footer-register.png" });
});
