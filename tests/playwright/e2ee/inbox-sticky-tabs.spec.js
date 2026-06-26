const { expect, test } = require("@playwright/test");

const TEST_PASSWORD = "Test-testtesttesttest-1";

async function login(page, username) {
  await page.addInitScript(() => {
    localStorage.setItem("hasFinishedGuidance", "true");
    sessionStorage.setItem("hushline:first-load-splash-seen", "true");
  });
  await page.goto("/login", { waitUntil: "networkidle" });
  await page.fill("#username", username);
  await page.fill("#password", TEST_PASSWORD);

  await Promise.all([
    page.waitForFunction(() => document.body?.dataset.authenticated === "true"),
    page.locator('button[type="submit"]').click(),
  ]);
}

test("inbox tabs keep the desktop top margin while pinned", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 500 });
  await login(page, "jerryseinfeld");

  await page.goto("/inbox", { waitUntil: "networkidle" });
  await expect(page.locator(".inbox-tabs-nav")).toBeVisible();
  await page.evaluate(() => {
    const messageList = document.querySelector(".message-list");
    const spacer = document.createElement("div");
    spacer.style.height = "900px";
    messageList?.append(spacer);
  });

  await page.evaluate(() => window.scrollTo(0, 200));

  await expect
    .poll(() =>
      page.evaluate(() => {
        const header = document.querySelector("header");
        const tabs = document.querySelector(".inbox-tabs-nav");

        if (!header || !tabs) {
          return Number.POSITIVE_INFINITY;
        }

        const headerRect = header.getBoundingClientRect();
        const tabsRect = tabs.getBoundingClientRect();
        const expectedMargin = Number.parseFloat(
          window.getComputedStyle(document.documentElement).fontSize,
        );

        return Math.abs(tabsRect.top - headerRect.bottom - expectedMargin);
      }),
    )
    .toBeLessThanOrEqual(1);
});
