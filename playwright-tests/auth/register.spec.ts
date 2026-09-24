import { test, expect } from "@playwright/test";
import { RegisterPage } from "../pom/RegisterPage";

const PASSWORD = "password123";
const EMAIL = "e2e@example.com";

test.describe("Register flow", () => {
  test("register page renders sign up form", async ({ page }) => {
    const registerPage = new RegisterPage(page);
    await registerPage.goto();
    await expect(registerPage.emailInput()).toBeVisible();
    await expect(registerPage.passwordInput()).toBeVisible();
    await expect(registerPage.signInLink()).toBeVisible();
  });

  test("duplicate email shows error", async ({ page }) => {
    const registerPage = new RegisterPage(page);
    await registerPage.goto();
    await registerPage.register(EMAIL, PASSWORD);
    await expect(page.getByText(/Email already registered/i)).toBeVisible();
  });

  test("valid registration redirects to /login", async ({ page }) => {
    const registerPage = new RegisterPage(page);
    const email = `e2e+${Date.now()}@example.com`;
    await registerPage.goto();
    await registerPage.register(email, PASSWORD);
    await expect(page).toHaveURL(/\/login/);
  });
});
