import { test, expect } from "@playwright/test";
import { MOCK_QUERY_RESPONSE, mockQueryRoute } from "../mocks/query";

test.describe("Search page", () => {
  test("renders the search form", async ({ page }) => {
    await page.goto("/search");

    await expect(page.getByText("Search knowledge base")).toBeVisible();
    await expect(page.getByLabel("Question")).toBeVisible();
    await expect(page.getByRole("button", { name: "Current" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Historical" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Search" })).toBeVisible();
  });

  test("submit button is disabled when question is empty", async ({ page }) => {
    await page.goto("/search");

    const submitBtn = page.getByRole("button", { name: "Search" });
    await expect(submitBtn).toBeDisabled();

    await page.getByLabel("Question").fill("a question");
    await expect(submitBtn).toBeEnabled();
  });

  test("mode toggle switches between Current and Historical", async ({
    page,
  }) => {
    await page.goto("/search");

    const currentBtn = page.getByRole("button", { name: "Current" });
    const historicalBtn = page.getByRole("button", { name: "Historical" });

    // Current is selected by default.
    await expect(currentBtn).toHaveAttribute("aria-pressed", "true");
    await expect(historicalBtn).toHaveAttribute("aria-pressed", "false");

    await historicalBtn.click();
    await expect(historicalBtn).toHaveAttribute("aria-pressed", "true");
    await expect(currentBtn).toHaveAttribute("aria-pressed", "false");
  });

  test("submits question and shows answer", async ({ page }) => {
    await mockQueryRoute(page);
    await page.goto("/search");

    await page.getByLabel("Question").fill("What documents are available?");
    await page.getByRole("button", { name: "Search" }).click();

    await expect(
      page.getByRole("button", { name: "Searching..." }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Searching..." }),
    ).toBeDisabled();

    await expect(page.getByRole("button", { name: "Search" })).toBeEnabled();

    await expect(page.getByText("Answer")).toBeVisible();
    await expect(page.getByText(MOCK_QUERY_RESPONSE.answer)).toBeVisible();
  });

  test("displays citation fields when sources are returned", async ({
    page,
  }) => {
    await mockQueryRoute(page);
    await page.goto("/search");

    await page.getByLabel("Question").fill("What documents are available?");
    await page.getByRole("button", { name: "Search" }).click();

    await expect(page.getByRole("button", { name: "Search" })).toBeEnabled();

    await expect(page.getByText("Sources")).toBeVisible();
    const firstCitation = page.locator("li").first();
    await expect(firstCitation).toContainText("Version");
  });
});
