import { Page } from "@playwright/test";

export const MOCK_QUERY_RESPONSE = {
  answer: "This is a mocked answer from the knowledge base.",
  citations: [
    {
      document_title: "Test Document",
      version_number: 1,
      status: "ACTIVE",
      updated_at: "2024-01-01T00:00:00.000000+00:00",
    },
  ],
};

export async function mockQueryRoute(page: Page) {
  await page.route("**/query", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_QUERY_RESPONSE),
      });
    } else {
      await route.continue();
    }
  });
}
