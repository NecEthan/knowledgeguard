import { test, expect } from "@playwright/test";
import { DocumentsPage } from "../pom/DocumentsPage";
import { VersionHistoryPage } from "../pom/VersionHistoryPage";

test.describe("Version History", () => {
  test("version history page shows uploaded document's first version", async ({
    page,
  }) => {
    const documentsPage = new DocumentsPage(page);
    const versionHistoryPage = new VersionHistoryPage(page);
    const docTitle = `Versioned doc ${Date.now()}`;

    await documentsPage.goto();
    await documentsPage.uploadDocument(docTitle, "v1.txt", "This is version one.");
    await documentsPage.openVersionHistory(docTitle);

    await versionHistoryPage.assertLoaded();
    await expect(versionHistoryPage.versionRows()).toHaveCount(1);
    await expect(versionHistoryPage.versionRows().first()).toContainText("v1");
  });

  test("uploading a new version appears in version history list", async ({
    page,
  }) => {
    const documentsPage = new DocumentsPage(page);
    const versionHistoryPage = new VersionHistoryPage(page);
    const docTitle = `Multi-version doc ${Date.now()}`;

    await documentsPage.goto();
    await documentsPage.uploadDocument(docTitle, "v1.txt", "Version one content.");
    await documentsPage.openVersionHistory(docTitle);

    await versionHistoryPage.assertLoaded();
    await expect(versionHistoryPage.versionRows()).toHaveCount(1);

    await versionHistoryPage.uploadNewVersion("v2.txt", "Version two content.");

    await expect(versionHistoryPage.versionRows()).toHaveCount(2);
    await expect(versionHistoryPage.versionRows().first()).toContainText("v2");
    await expect(versionHistoryPage.versionRows().nth(1)).toContainText("v1");
  });

  test("back to documents button returns to documents page", async ({
    page,
  }) => {
    const documentsPage = new DocumentsPage(page);
    const versionHistoryPage = new VersionHistoryPage(page);
    const docTitle = `Nav test doc ${Date.now()}`;

    await documentsPage.goto();
    await documentsPage.uploadDocument(docTitle, "nav.txt", "Navigation test.");
    await documentsPage.openVersionHistory(docTitle);

    await versionHistoryPage.assertLoaded();
    await versionHistoryPage.goBackToDocuments();
    await expect(page).toHaveURL(/\/documents$/);
  });

  test("can set a previous version as active", async ({ page }) => {
    const documentsPage = new DocumentsPage(page);
    const versionHistoryPage = new VersionHistoryPage(page);
    const docTitle = `Activate test doc ${Date.now()}`;

    // Upload v1 and open version history.
    await documentsPage.goto();
    await documentsPage.uploadDocument(docTitle, "v1.txt", "Version one content.");
    await documentsPage.openVersionHistory(docTitle);
    await versionHistoryPage.assertLoaded();

    // Upload v2.
    await versionHistoryPage.uploadNewVersion("v2.txt", "Version two content.");
    await expect(versionHistoryPage.versionRows()).toHaveCount(2);

    // Wait for v2 to become ACTIVE (worker processes it).
    await versionHistoryPage.waitForVersionStatus(2, "ACTIVE");

    // Activate v1.
    await versionHistoryPage.clickSetAsActive(1);

    // v1 should now be ACTIVE, v2 should be SUPERSEDED.
    await versionHistoryPage.waitForVersionStatus(1, "ACTIVE");
    await versionHistoryPage.waitForVersionStatus(2, "SUPERSEDED");
  });
});
