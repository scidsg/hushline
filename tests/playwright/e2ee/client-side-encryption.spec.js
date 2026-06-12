const { expect, test } = require("@playwright/test");

const PGP_ARMOR_HEADER = "-----BEGIN PGP MESSAGE-----";
const contactPlaintext = "P0 frontend e2ee contact sentinel";
const messagePlaintext = "P0 frontend e2ee message sentinel";

function captchaAnswer(labelText) {
  const match = labelText.match(/(\d+)\s*\+\s*(\d+)/);
  expect(
    match,
    `CAPTCHA label should be parseable: ${labelText}`,
  ).not.toBeNull();
  return String(Number(match[1]) + Number(match[2]));
}

test("JS-enabled profile submissions encrypt fields before the POST leaves the browser", async ({
  page,
}) => {
  const consoleErrors = [];
  const pageErrors = [];
  let capturedPostBody = null;

  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    pageErrors.push(error.message);
  });
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/to/admin")) {
      capturedPostBody = request.postData() || "";
    }
  });

  await page.goto("/to/admin", { waitUntil: "networkidle" });
  await page.evaluate(() => {
    localStorage.setItem("hasFinishedGuidance", "true");
    document.getElementById("guidance-modal")?.classList.remove("show");
  });

  await expect(page.locator("#messageForm")).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () => document.getElementById("recipientPublicKeys")?.textContent || "",
      ),
    )
    .toContain("BEGIN PGP PUBLIC KEY BLOCK");
  await expect(
    page.locator('script[src$="/static/js/client-side-encryption.js"]'),
  ).toHaveCount(1);

  await expect
    .poll(() => page.evaluate(() => window.isSecureContext))
    .toBe(true);

  await page.fill("#field_0", contactPlaintext);
  await page.fill("#field_1", messagePlaintext);
  await page.fill(
    "#captcha_answer",
    captchaAnswer(
      await page.locator('label[for="captcha_answer"]').innerText(),
    ),
  );

  await Promise.all([
    page.waitForRequest(
      (request) =>
        request.method() === "POST" && request.url().endsWith("/to/admin"),
    ),
    page.locator("#submitBtn").click(),
  ]);

  expect(pageErrors).toEqual([]);
  expect(
    consoleErrors.filter(
      (message) =>
        !message.includes("Permissions-Policy header") &&
        !message.includes("Failed to load resource"),
    ),
  ).toEqual([]);
  expect(capturedPostBody).toBeTruthy();

  const params = new URLSearchParams(capturedPostBody);
  const encryptedContact = params.get("field_0") || "";
  const encryptedMessage = params.get("field_1") || "";
  const encryptedEmailBody = params.get("encrypted_email_body") || "";

  expect(encryptedContact).toContain(PGP_ARMOR_HEADER);
  expect(encryptedMessage).toContain(PGP_ARMOR_HEADER);
  expect(encryptedEmailBody).toContain(PGP_ARMOR_HEADER);

  expect(encryptedContact).not.toContain(contactPlaintext);
  expect(encryptedMessage).not.toContain(messagePlaintext);
  expect(encryptedEmailBody).not.toContain(contactPlaintext);
  expect(encryptedEmailBody).not.toContain(messagePlaintext);
});
