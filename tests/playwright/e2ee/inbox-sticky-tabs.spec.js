const { expect, test } = require("@playwright/test");

const TEST_PASSWORD = "Test-testtesttesttest-1";

for (const width of [390, 1280]) {
  test(`inbox badge borders fit their scroll container at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 700 });
    await login(page, "jerryseinfeld");
    await page.goto("/inbox", { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);

    for (const padding of ["0.25rem", "0.215rem", "0.125rem"]) {
      await page.locator(".inbox-tabs .badge").evaluateAll((badges, value) => {
        for (const badge of badges) badge.style.paddingBlock = value;
      }, padding);
      const badges = page.locator(".inbox-tabs .badge");
      expect(await badges.count()).toBeGreaterThan(0);
      for (const badge of await badges.all()) {
        await badge.scrollIntoViewIfNeeded();
        const fits = await badge.evaluate((element) => {
          const bounds = element.getBoundingClientRect();
          const tabs = element.closest(".inbox-tabs").getBoundingClientRect();
          return bounds.top >= tabs.top && bounds.bottom <= tabs.bottom;
        });
        expect(
          fits,
          `badge border must fit with ${padding} vertical padding`,
        ).toBe(true);
      }
    }
  });
}

for (const width of [1280, 390]) {
  test(`inbox count badges remain fully visible at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    await login(page, "jerryseinfeld");
    await page.goto("/inbox", { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);
    const badges = page.locator(".inbox-tabs .badge");
    await expect(badges.first()).toBeVisible();
    const clipped = await badges.evaluateAll((elements) =>
      elements.flatMap((badge) => {
        const box = badge.getBoundingClientRect();
        const range = document.createRange();
        range.selectNodeContents(badge);
        const text = range.getBoundingClientRect();
        if (text.top < box.top + 1 || text.bottom > box.bottom - 1) {
          return ["count text touches or exceeds the badge border"];
        }
        for (
          let parent = badge.parentElement;
          parent;
          parent = parent.parentElement
        ) {
          const style = getComputedStyle(parent);
          if (["hidden", "clip", "auto", "scroll"].includes(style.overflowY)) {
            const top = parent.getBoundingClientRect().top + parent.clientTop;
            if (
              box.top < top - 0.5 ||
              box.bottom > top + parent.clientHeight + 0.5
            ) {
              return ["badge clipped by a scrolling ancestor"];
            }
          }
        }
        return [];
      }),
    );
    expect(clipped).toEqual([]);
  });
}

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
