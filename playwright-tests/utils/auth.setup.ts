import { test as setup, expect } from "@playwright/test";
import fs from "fs";

const EMAIL = "e2e@example.com";
const PASSWORD = "password123";
const API = "http://localhost:8000";

setup("seed and authenticate", async ({ page }) => {
  const res = await fetch(`${API}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  if (!res.ok && res.status !== 409) throw new Error(`seed failed: ${res.status}`);

  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/dashboard/);

  fs.mkdirSync("playwright/.auth", { recursive: true });
  await page.context().storageState({ path: "playwright/.auth/user.json" });
});
