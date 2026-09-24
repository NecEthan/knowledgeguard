import { test, expect } from "@playwright/test";
import { LoginPage } from "../pom/LoginPage";

const EMAIL = "e2e@example.com";
const PASSWORD = "password123";

test.describe("Auth flow", () => {
  test("unauthenticated root redirects to /login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);
  });

  test("unauthenticated /documents redirects to /login", async ({ page }) => {
    await page.goto("/documents");
    await expect(page).toHaveURL(/\/login/);
  });

  test("login page renders sign in form", async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await expect(loginPage.emailInput()).toBeVisible();
    await expect(loginPage.passwordInput()).toBeVisible();
    await expect(loginPage.signInButton()).toBeVisible();
  });

  test("wrong password shows error", async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login(EMAIL, "wrongpassword");
    await expect(page.getByRole("alert")).toBeVisible();
  });

  test("valid login redirects to /documents", async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login(EMAIL, PASSWORD);
    await expect(page).toHaveURL(/\/documents/);
    await expect(page.getByText(EMAIL)).toBeVisible();
  });

  test("sign out returns to /login", async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.login(EMAIL, PASSWORD);
    await expect(page).toHaveURL(/\/documents/);
    await loginPage.signOut();
    await expect(page).toHaveURL(/\/login/);
  });
});
