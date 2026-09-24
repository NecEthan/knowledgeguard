import { test, expect } from "@playwright/test";

test.describe("Version History", () => {
  test("version history page shows uploaded document's first version", async ({
    page,
  }) => {
    await page.goto("/documents");

    const docTitle = `Versioned doc ${Date.now()}`;

    await page.getByLabel("Title").fill(docTitle);
    await page.getByLabel("File").setInputFiles({
      name: "v1.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("This is version one."),
    });
    await page.getByRole("button", { name: /upload document/i }).click();
    await expect(page.getByText(docTitle)).toBeVisible();

    const row = page.getByTestId("document-row").filter({ hasText: docTitle });
    await row.getByRole("link", { name: /versions/i }).click();

    await expect(page.getByText(/version history/i)).toBeVisible();
    await expect(page.getByTestId("version-row")).toHaveCount(1);
    await expect(page.getByTestId("version-row").first()).toContainText("v1");
  });

  test("uploading a new version appears in version history list", async ({
    page,
  }) => {
    await page.goto("/documents");

    const docTitle = `Multi-version doc ${Date.now()}`;

    await page.getByLabel("Title").fill(docTitle);
    await page.getByLabel("File").setInputFiles({
      name: "v1.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Version one content."),
    });
    await page.getByRole("button", { name: /upload document/i }).click();
    await expect(page.getByText(docTitle)).toBeVisible();

    const row = page.getByTestId("document-row").filter({ hasText: docTitle });
    await row.getByRole("link", { name: /versions/i }).click();

    await expect(page.getByText(/version history/i)).toBeVisible();
    await expect(page.getByTestId("version-row")).toHaveCount(1);

    // Upload version 2
    await page.getByLabel("File").setInputFiles({
      name: "v2.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Version two content."),
    });
    await page.getByRole("button", { name: /upload new version/i }).click();

    await expect(page.getByTestId("version-row")).toHaveCount(2);

    // Newest first
    const versionRows = page.getByTestId("version-row");
    await expect(versionRows.first()).toContainText("v2");
    await expect(versionRows.nth(1)).toContainText("v1");
  });

  test("back to documents button returns to documents page", async ({ page }) => {
    await page.goto("/documents");

    const docTitle = `Nav test doc ${Date.now()}`;

    await page.getByLabel("Title").fill(docTitle);
    await page.getByLabel("File").setInputFiles({
      name: "nav.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Navigation test."),
    });
    await page.getByRole("button", { name: /upload document/i }).click();
    await expect(page.getByText(docTitle)).toBeVisible();

    const row = page.getByTestId("document-row").filter({ hasText: docTitle });
    await row.getByRole("link", { name: /versions/i }).click();

    await expect(page.getByText(/version history/i)).toBeVisible();
    await page.getByRole("button", { name: /back to documents/i }).click();
    await expect(page).toHaveURL(/\/documents$/);
  });
});
