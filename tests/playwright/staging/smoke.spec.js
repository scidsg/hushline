const { expect, test } = require("@playwright/test");

function expectSecurityHeaders(response) {
  const headers = response.headers();
  expect(headers["content-security-policy"]).toContain("default-src 'self'");
  expect(headers["content-security-policy"]).toContain(
    "frame-ancestors 'none'",
  );
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["referrer-policy"]).toBe("no-referrer");
}

test("staging exposes healthy public and authentication surfaces", async ({
  page,
  request,
}) => {
  const health = await request.get("/health.json");
  expect(health.status()).toBe(200);
  await expect(health.json()).resolves.toMatchObject({ status: "ok" });

  const directory = await page.goto("/directory", { waitUntil: "networkidle" });
  expect(directory).not.toBeNull();
  expect(directory.status()).toBe(200);
  expectSecurityHeaders(directory);
  await expect(page.locator("body")).toHaveAttribute(
    "data-authenticated",
    "false",
  );
  await expect
    .poll(() => page.evaluate(() => window.isSecureContext))
    .toBe(true);

  const registration = await page.goto("/register", {
    waitUntil: "networkidle",
  });
  expect(registration).not.toBeNull();
  expect(registration.status()).toBe(200);
  expectSecurityHeaders(registration);
  await expect(page.locator("main")).toBeVisible();

  const login = await page.goto("/login", { waitUntil: "networkidle" });
  expect(login).not.toBeNull();
  expect(login.status()).toBe(200);
  expectSecurityHeaders(login);
  await expect(page.locator("#username")).toBeVisible();
  await expect(page.locator("#password")).toBeVisible();
});
