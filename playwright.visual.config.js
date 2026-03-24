const { defineConfig } = require("@playwright/test");
const manifest = require("./docs/screenshots/scenes.json");

const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://host.docker.internal:8080";
const secureOrigin = new URL(baseURL).origin;

const projects = manifest.viewports.map((viewport) => ({
  name: viewport.id,
  use: {
    viewport: {
      width: viewport.width,
      height: viewport.height,
    },
    isMobile: viewport.isMobile === true,
    hasTouch: viewport.hasTouch === true,
    deviceScaleFactor: viewport.deviceScaleFactor || 1,
  },
}));

module.exports = defineConfig({
  testDir: "./tests/playwright",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [
    ["list"],
    ["html", { open: "never" }],
  ],
  outputDir: "test-results/playwright-visual",
  use: {
    baseURL,
    browserName: "chromium",
    locale: "en-US",
    timezoneId: "UTC",
    launchOptions: {
      args: [
        "--font-render-hinting=none",
        `--unsafely-treat-insecure-origin-as-secure=${secureOrigin}`,
      ],
    },
  },
  projects,
});
