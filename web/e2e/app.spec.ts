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

  const logoutResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/v1/auth/logout") && response.status() === 204,
  );
  await page.getByRole("button", { name: "退出登录" }).click();
  await logoutResponse;
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("button", { exact: true, name: "登录" })).toBeVisible();
  await expect(page.evaluate(() => window.localStorage.getItem("hx_token"))).resolves.toBeNull();
});
