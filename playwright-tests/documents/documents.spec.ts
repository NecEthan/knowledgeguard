import { test, expect } from "@playwright/test";

test.describe("Documents", () => {
  test("documents page renders", async ({ page }) => {
    await page.goto("/documents");
    await expect(page.getByText(/upload document/i).first()).toBeVisible();
    await expect(page.getByText(/your documents/i)).toBeVisible();
  });

  test("upload form renders with file input and title", async ({ page }) => {
    await page.goto("/documents");
    await expect(page.getByLabel("File")).toBeVisible();
    await expect(page.getByLabel("Title")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /upload document/i }),
    ).toBeVisible();
  });

  test("upload a text document and see it in the list", async ({ page }) => {
    await page.goto("/documents");

    const docTitle = `E2E test doc ${Date.now()}`;

    await page.getByLabel("Title").fill(docTitle);
    await page.getByLabel("File").setInputFiles({
      name: "test.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("This is a KnowledgeGuard E2E test document."),
    });

    await page.getByRole("button", { name: /upload document/i }).click();

    await expect(page.getByText(docTitle)).toBeVisible();
  });

  test("delete a document removes it from the list", async ({ page }) => {
    await page.goto("/documents");

    const docTitle = `E2E delete test ${Date.now()}`;

    // Upload first
    await page.getByLabel("Title").fill(docTitle);
    await page.getByLabel("File").setInputFiles({
      name: "delete-me.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Delete this document."),
    });
    await page.getByRole("button", { name: /upload document/i }).click();
    await expect(page.getByText(docTitle)).toBeVisible();

    // Delete it
    const row = page.getByTestId("document-row").filter({ hasText: docTitle });
    await row.getByRole("button", { name: /delete/i }).click();

    await expect(page.getByText(docTitle)).not.toBeVisible();
  });
});
