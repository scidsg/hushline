const { defineConfig } = require("@playwright/test");
module.exports = defineConfig({
  testDir: "./tests/playwright",
  testMatch: "payment-return.spec.js",
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    browserName: "chromium",
    headless: true,
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    },
  },
});
