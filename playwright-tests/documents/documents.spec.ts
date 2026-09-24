import { test, expect } from "@playwright/test";
import { DocumentsPage } from "../pom/DocumentsPage";

test.describe("Documents", () => {
  test("documents page renders", async ({ page }) => {
    const documentsPage = new DocumentsPage(page);
    await documentsPage.goto();
    await documentsPage.assertPageVisible();
  });

  test("upload form renders with file input and title", async ({ page }) => {
    const documentsPage = new DocumentsPage(page);
    await documentsPage.goto();
    await documentsPage.assertUploadFormVisible();
  });

  test("upload a text document and see it in the list", async ({ page }) => {
    const documentsPage = new DocumentsPage(page);
    const docTitle = `E2E test doc ${Date.now()}`;

    await documentsPage.goto();
    await documentsPage.uploadDocument(
      docTitle,
      "test.txt",
      "This is a KnowledgeGuard E2E test document.",
    );

    await expect(page.getByText(docTitle)).toBeVisible();
  });

  test("delete a document removes it from the list", async ({ page }) => {
    const documentsPage = new DocumentsPage(page);
    const docTitle = `E2E delete test ${Date.now()}`;

    await documentsPage.goto();
    await documentsPage.uploadDocument(
      docTitle,
      "delete-me.txt",
      "Delete this document.",
    );
    await documentsPage.deleteDocument(docTitle);

    await expect(page.getByText(docTitle)).not.toBeVisible();
  });
});
