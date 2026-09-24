import { test, expect } from "@playwright/test";
import { SearchPage } from "../pom/SearchPage";
import { MOCK_QUERY_RESPONSE } from "../mocks/query";

test.describe("Search page", () => {
  test("renders the search form", async ({ page }) => {
    const searchPage = new SearchPage(page);
    await searchPage.goto();
    await expect(page.getByText("Search knowledge base")).toBeVisible();
    await expect(searchPage.questionInput()).toBeVisible();
    await expect(searchPage.currentModeButton()).toBeVisible();
    await expect(searchPage.historicalModeButton()).toBeVisible();
    await expect(searchPage.searchButton()).toBeVisible();
  });

  test("submit button is disabled when question is empty", async ({ page }) => {
    const searchPage = new SearchPage(page);
    await searchPage.goto();
    await expect(searchPage.searchButton()).toBeDisabled();

    await searchPage.questionInput().fill("a question");
    await expect(searchPage.searchButton()).toBeEnabled();
  });

  test("mode toggle switches between Current and Historical", async ({
    page,
  }) => {
    const searchPage = new SearchPage(page);
    await searchPage.goto();

    await expect(searchPage.currentModeButton()).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(searchPage.historicalModeButton()).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    await searchPage.historicalModeButton().click();
    await expect(searchPage.historicalModeButton()).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(searchPage.currentModeButton()).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  test("submits question and shows answer", async ({ page }) => {
    const searchPage = new SearchPage(page);
    await searchPage.gotoWithMock();
    await searchPage.search("What documents are available?");

    await expect(searchPage.searchingButton()).toBeVisible();
    await expect(searchPage.searchingButton()).toBeDisabled();
    await expect(searchPage.searchButton()).toBeEnabled();

    await expect(page.getByText("Answer")).toBeVisible();
    await expect(page.getByText(MOCK_QUERY_RESPONSE.answer)).toBeVisible();
  });

  test("displays citation fields when sources are returned", async ({
    page,
  }) => {
    const searchPage = new SearchPage(page);
    await searchPage.gotoWithMock();
    await searchPage.search("What documents are available?");

    await expect(searchPage.searchButton()).toBeEnabled();

    await expect(page.getByText("Sources")).toBeVisible();
    const firstCitation = page.locator("li").first();
    await expect(firstCitation).toContainText("Version");
  });
});
