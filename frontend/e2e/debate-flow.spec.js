import { test, expect } from "@playwright/test";

const apiURL = process.env.PLAYWRIGHT_API_URL || "http://127.0.0.1:9000";

test.describe("辩论室 E2E", () => {
  test.beforeEach(async ({ request }) => {
    const health = await request.get(`${apiURL}/health`).catch(() => null);
    test.skip(!health?.ok(), "后端未启动（需 http://127.0.0.1:9000）");
  });

  test("创建房间并看到首条流式或已发布发言", async ({ page }) => {
    await page.goto("/");

    const quickDemo = page.getByTestId("schedule-quick_demo");
    if (await quickDemo.isVisible()) {
      await quickDemo.click();
    }

    await page.getByTestId("home-enter-room").click();
    await page.waitForURL(/\/room\/(?!demo)/, { timeout: 30_000 });

    const board = page.getByTestId("debate-message-board");
    await expect(board).toBeVisible();

    const streaming = page.getByTestId("debate-streaming");
    const published = page.locator(".message-board .message .md-body");

    await expect(streaming.or(published.first())).toBeVisible({ timeout: 90_000 });

    const hasStream = await streaming.isVisible().catch(() => false);
    if (hasStream) {
      await expect(streaming.locator(".md-body")).not.toBeEmpty();
    } else {
      await expect(published.first()).not.toBeEmpty();
    }
  });
});
