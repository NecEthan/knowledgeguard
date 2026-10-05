import { type Page, type Locator } from "@playwright/test";
import { expect } from "@playwright/test";

export class VersionHistoryPage {
  constructor(private readonly page: Page) {}

  async assertLoaded() {
    await expect(this.page.getByText(/version history/i)).toBeVisible();
  }

  versionRows(): Locator {
    return this.page.getByTestId("version-row");
  }

  async uploadNewVersion(filename: string, content: string) {
    await this.page.getByLabel("File").setInputFiles({
      name: filename,
      mimeType: "text/plain",
      buffer: Buffer.from(content),
    });
    await this.page
      .getByRole("button", { name: /upload new version/i })
      .click();
  }

  async goBackToDocuments() {
    await this.page
      .getByRole("button", { name: /back to documents/i })
      .click();
  }

  async waitForVersionStatus(versionNumber: number, status: string) {
    await this.page
      .getByTestId("version-row")
      .filter({ hasText: `v${versionNumber}` })
      .getByTestId("version-status")
      .filter({ hasText: status })
      .waitFor({ state: "visible" });
  }

  async clickSetAsActive(versionNumber: number) {
    await this.page
      .getByTestId("version-row")
      .filter({ hasText: `v${versionNumber}` })
      .getByRole("button", { name: /set as active/i })
      .click();
  }
}
