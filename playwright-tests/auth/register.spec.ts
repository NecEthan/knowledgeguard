import { test, expect } from "@playwright/test";

const PASSWORD = "password123";
const EMAIL = "e2e@example.com";

test.describe("Register flow", () => {
  test("register page renders sign up form", async ({ page }) => {
    await page.goto("/register");
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByRole("link", { name: /Sign in/i })).toBeVisible();
  });

  test("duplicate email shows error", async ({ page }) => {
    await page.goto("/register");
    await page.getByLabel("Email").fill(EMAIL);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: /Create account/i }).click();
    await expect(page.getByText(/Email already registered/i)).toBeVisible();
  });

  test("valid registration redirects to /login", async ({ page }) => {
    const email = `e2e+${Date.now()}@example.com`;
    await page.goto("/register");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: /Create account/i }).click();
    await expect(page).toHaveURL(/\/login/);
  });
});
