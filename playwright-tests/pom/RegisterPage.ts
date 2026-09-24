import { type Page } from "@playwright/test";

export class RegisterPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/register");
  }

  async register(email: string, password: string) {
    await this.page.getByLabel("Email").fill(email);
    await this.page.getByLabel("Password").fill(password);
    await this.page.getByRole("button", { name: /create account/i }).click();
  }

  emailInput() {
    return this.page.getByLabel("Email");
  }

  passwordInput() {
    return this.page.getByLabel("Password");
  }

  signInLink() {
    return this.page.getByRole("link", { name: /sign in/i });
  }
}
