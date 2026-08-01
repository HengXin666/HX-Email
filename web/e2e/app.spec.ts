import { expect, test } from "@playwright/test";

test("protects the workbench and recovers from a rejected login", async ({ page }) => {
  await page.goto("/overview");
  await expect(page).toHaveURL(/\/login$/);

  const username = page.getByLabel("用户名", { exact: true });
  const password = page.getByLabel("密码", { exact: true });
  const loginButton = page.getByRole("button", { exact: true, name: "登录" });

  await username.fill("admin");
  await password.fill("wrong-password");
  const rejectedLogin = page.waitForResponse(
    (response) => response.url().endsWith("/api/v1/auth/login") && response.status() === 401,
  );
  await loginButton.click();
  await rejectedLogin;
  await expect(page.getByText("Invalid username or password")).toBeVisible();

  await password.fill("admin");
  const acceptedLogin = page.waitForResponse(
    (response) => response.url().endsWith("/api/v1/auth/login") && response.status() === 200,
  );
  await loginButton.click();
  await acceptedLogin;

  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByRole("heading", { name: "邮箱工作台" })).toBeVisible();
  await expect(page.getByText("admin", { exact: true })).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  const overviewScroller = page.locator("div.overflow-y-auto.p-4").first();
  await overviewScroller.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await expect(page.getByText("所有邮箱的最新邮件", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "最新邮件", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "打开工作台", exact: true })).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);

  await page.goto("/settings");
  await page.getByRole("button", { name: "自动化", exact: true }).click();
  await expect(page.getByText("自动轮询", { exact: true })).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);

  const logoutResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/v1/auth/logout") && response.status() === 204,
  );
  await page.getByRole("button", { name: "退出登录" }).click();
  await logoutResponse;
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("button", { exact: true, name: "登录" })).toBeVisible();
  await expect(page.evaluate(() => window.localStorage.getItem("hx_token"))).resolves.toBeNull();
});
