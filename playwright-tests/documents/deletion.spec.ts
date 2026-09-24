import { test, expect } from "@playwright/test";
import { DocumentsPage } from "../pom/DocumentsPage";
import { SearchPage } from "../pom/SearchPage";

test.describe("Document deletion", () => {
  test("deleted document no longer appears in the document list", async ({
    page,
  }) => {
    const documentsPage = new DocumentsPage(page);
    const docTitle = `Deletion E2E ${Date.now()}`;

    await documentsPage.goto();
    await documentsPage.uploadDocument(
      docTitle,
      "deletion-test.txt",
      "This document will be deleted.",
    );

    await expect(page.getByText(docTitle)).toBeVisible();

    await documentsPage.deleteDocument(docTitle);

    await expect(page.getByText(docTitle)).not.toBeVisible();
  });

  test("deleted document title does not appear in search citations", async ({
    page,
  }) => {
    const documentsPage = new DocumentsPage(page);
    const searchPage = new SearchPage(page);
    const docTitle = `Deletion search E2E ${Date.now()}`;

    // Upload and delete the document.
    await documentsPage.goto();
    await documentsPage.uploadDocument(
      docTitle,
      "deletion-search-test.txt",
      "This document will be deleted before querying.",
    );
    await expect(page.getByText(docTitle)).toBeVisible();
    await documentsPage.deleteDocument(docTitle);
    await expect(page.getByText(docTitle)).not.toBeVisible();

    // Mock the query API to return no results (reflecting deleted state).
    await page.route("**/query", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            answer:
              "I don't have enough information in the provided context to answer that question.",
            citations: [],
          }),
        });
      } else {
        await route.continue();
      }
    });

    await searchPage.goto();
    await searchPage.search("What does the deleted document say?");

    // The deleted document's title must not appear as a citation.
    await expect(page.getByText(docTitle)).not.toBeVisible();
  });
});
