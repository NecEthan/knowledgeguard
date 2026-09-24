import { type Page, type Locator } from "@playwright/test";
import { mockQueryRoute } from "../mocks/query";

export class SearchPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/search");
  }

  async gotoWithMock() {
    await mockQueryRoute(this.page);
    await this.page.goto("/search");
  }

  questionInput(): Locator {
    return this.page.getByLabel("Question");
  }

  searchButton(): Locator {
    return this.page.getByRole("button", { name: "Search" });
  }

  searchingButton(): Locator {
    return this.page.getByRole("button", { name: "Searching..." });
  }

  currentModeButton(): Locator {
    return this.page.getByRole("button", { name: "Current" });
  }

  historicalModeButton(): Locator {
    return this.page.getByRole("button", { name: "Historical" });
  }

  async search(question: string) {
    await this.questionInput().fill(question);
    await this.searchButton().click();
  }
}
