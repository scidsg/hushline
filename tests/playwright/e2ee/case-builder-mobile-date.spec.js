const { test, expect, chromium, webkit, devices } = require("@playwright/test");

for (const [name, browserType, device] of [
  ["chromium", chromium, "Pixel 7"],
  ["webkit", webkit, "iPhone 13 Mini"],
]) {
  test(`mobile date field matches single-row inputs in ${name}`, async ({
    baseURL,
  }, testInfo) => {
    const browser = await browserType.launch();
    try {
      const context = await browser.newContext({
        ...devices[device],
        deviceScaleFactor: 1,
        baseURL,
      });
      const page = await context.newPage();
      for (const width of [320, 390, 640]) {
        await page.setViewportSize({ width, height: 900 });
        await page.goto("/case-builder", { waitUntil: "networkidle" });
        const date = page.locator("#case-event-date");
        const text = page.locator("#case-evidence-title-input");
        const properties = (field) =>
          field.evaluate((element) => {
            const style = getComputedStyle(element);
            return Object.fromEntries(
              [
                "height",
                "fontFamily",
                "fontSize",
                "paddingTop",
                "paddingBottom",
                "paddingLeft",
                "borderTopWidth",
                "borderRadius",
              ].map((property) => [property, style[property]]),
            );
          });
        expect(await properties(date)).toEqual(await properties(text));
        await expect(date).toHaveCSS("height", "44px");
        await expect(date).toHaveCSS("width", "224px");
        await expect(date).toHaveCSS("appearance", "none");
        await date.screenshot({
          path: testInfo.outputPath(`${name}-${width}-date-empty.png`),
        });
        await date.fill("2026-09-22");
        await date.blur();
        await text.fill("09/22/2026");
        await text.blur();
        await expect(date).toHaveValue("2026-09-22");
        await expect(date).toHaveCSS("height", "44px");
        const wrapper = page.locator(".case-builder-date");
        const bounds = await wrapper.boundingBox();
        const icon = await wrapper.locator("svg").boundingBox();
        expect(
          Math.abs(icon.y + icon.height / 2 - bounds.y - bounds.height / 2),
        ).toBeLessThan(1);
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
        await wrapper.screenshot({
          path: testInfo.outputPath(`${name}-${width}-date-filled.png`),
        });
        await text.screenshot({
          path: testInfo.outputPath(`${name}-${width}-text-input.png`),
        });
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth),
        ).toBe(width);
      }
    } finally {
      await browser.close();
    }
  });
}
