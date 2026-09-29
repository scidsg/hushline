const { expect, test } = require("@playwright/test");

const TEST_PASSWORD = "Test-testtesttesttest-1";
const VIRTUAL_TEST_USERNAMES = ["georgecostanza", "elainebenes"];

async function loginAndAuthorize(page, username = "jerryseinfeld") {
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

  await page.goto("/settings/security-keys", { waitUntil: "networkidle" });
  await page.fill("#password", TEST_PASSWORD);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.locator("#security-key-enrollment-form")).toBeVisible();
}

function syntheticRegistrationOptions() {
  return {
    rp: { id: "localhost", name: "Hush Line Test" },
    user: { id: "Ag", name: "jerryseinfeld", displayName: "Jerry" },
    challenge: "AQ",
    pubKeyCredParams: [{ type: "public-key", alg: -7 }],
    timeout: 300000,
    attestation: "none",
    excludeCredentials: [],
    authenticatorSelection: {
      residentKey: "discouraged",
      userVerification: "required",
    },
  };
}

async function installSyntheticSecurityKey(page) {
  await page.addInitScript(() => {
    Object.defineProperty(window, "PublicKeyCredential", {
      configurable: true,
      value: class PublicKeyCredential {},
    });
    Object.defineProperty(navigator, "credentials", {
      configurable: true,
      value: {
        create: async () => {
          if (window.__securityKeyFailure) {
            throw new DOMException(
              window.__securityKeyFailure,
              "NotAllowedError",
            );
          }
          return {
            id: "synthetic-key",
            rawId: new Uint8Array([3]).buffer,
            type: "public-key",
            authenticatorAttachment: "cross-platform",
            getClientExtensionResults: () => ({}),
            response: {
              attestationObject: new Uint8Array([4]).buffer,
              clientDataJSON: new Uint8Array([5]).buffer,
              getTransports: () => ["usb", "nfc"],
            },
          };
        },
      },
    });
  });
}

async function addVirtualSecurityKey(cdp, transport) {
  const { authenticatorId } = await cdp.send(
    "WebAuthn.addVirtualAuthenticator",
    {
      options: {
        protocol: "ctap2",
        ctap2Version: "ctap2_1",
        transport,
        hasResidentKey: true,
        hasUserVerification: true,
        isUserVerified: true,
        automaticPresenceSimulation: true,
      },
    },
  );
  return authenticatorId;
}

async function setVirtualSecurityKeyPresence(cdp, authenticatorId, enabled) {
  await cdp.send("WebAuthn.setAutomaticPresenceSimulation", {
    authenticatorId,
    enabled,
  });
}

async function enrollVirtualSecurityKey(page, label) {
  await page.getByLabel("Key Label").fill(label);
  await page.getByRole("button", { name: "Add Security Key" }).click();
  await expect(page.getByRole("status")).toContainText("Security key added");
}

async function authorizeAfterRecentStrongAuthentication(page) {
  await page.fill("#password", TEST_PASSWORD);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.locator("#security-key-enrollment-form")).toBeVisible();
}

async function loginWithSecurityKey(page, username) {
  await page.goto("/login", { waitUntil: "networkidle" });
  await page.fill("#username", username);
  await page.fill("#password", TEST_PASSWORD);
  await page.locator('button[type="submit"]').click();
  await expect(
    page.getByRole("button", { name: "Verify Security Key" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Verify Security Key" }).click();
  await expect(page.locator("body")).toHaveAttribute(
    "data-authenticated",
    "true",
  );
}

test("enrolls a primary and backup security key with keyboard and status feedback", async ({
  page,
}) => {
  await installSyntheticSecurityKey(page);
  const labels = [];
  const transports = [];
  await page.route("**/settings/security-keys/registration/options", (route) =>
    route.fulfill({ status: 200, json: syntheticRegistrationOptions() }),
  );
  await page.route(
    "**/settings/security-keys/registration/verify",
    async (route) => {
      const payload = route.request().postDataJSON();
      labels.push(payload.name);
      transports.push(payload.credential.response.transports);
      await route.fulfill({
        status: 201,
        json: {
          credential_id: labels.length,
          message:
            "Security key added. Keep a backup key in a separate safe place.",
        },
      });
    },
  );
  await loginAndAuthorize(page);

  const status = page.getByRole("status");
  await expect(status).toHaveAttribute("aria-live", "polite");
  await page.getByLabel("Key Label").fill("Primary USB key");
  await page.getByLabel("Key Label").press("Enter");
  await expect(status).toContainText("Security key added");

  await page.reload({ waitUntil: "networkidle" });
  await page.getByLabel("Key Label").fill("Backup NFC key");
  await page.getByRole("button", { name: "Add Security Key" }).click();
  await expect(status).toContainText("backup key");

  expect(labels).toEqual(["Primary USB key", "Backup NFC key"]);
  expect(transports).toEqual([
    ["usb", "nfc"],
    ["usb", "nfc"],
  ]);
});

test("cancellation and timeout leave enrollment available to retry", async ({
  page,
}) => {
  await installSyntheticSecurityKey(page);
  await page.route("**/settings/security-keys/registration/options", (route) =>
    route.fulfill({ status: 200, json: syntheticRegistrationOptions() }),
  );
  await loginAndAuthorize(page);

  for (const failure of ["canceled", "timed out"]) {
    await page.evaluate((value) => {
      window.__securityKeyFailure = value;
    }, failure);
    await page.getByLabel("Key Label").fill(`${failure} key`);
    await page.getByRole("button", { name: "Add Security Key" }).click();
    await expect(page.getByRole("status")).toContainText(
      "canceled or timed out. No security key was added",
    );
    await expect(
      page.getByRole("button", { name: "Add Security Key" }),
    ).toBeEnabled();
  }
});

test("unsupported browser capability prevents enrollment", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "PublicKeyCredential", {
      configurable: true,
      value: undefined,
    });
  });
  await loginAndAuthorize(page);
  await expect(page.getByRole("status")).toContainText(
    "browser cannot enroll security keys",
  );
  await expect(
    page.getByRole("button", { name: "Add Security Key" }),
  ).toBeDisabled();
});

test("network interruption after key response gives safe recovery guidance", async ({
  page,
}) => {
  await installSyntheticSecurityKey(page);
  await page.route("**/settings/security-keys/registration/options", (route) =>
    route.fulfill({ status: 200, json: syntheticRegistrationOptions() }),
  );
  await page.route("**/settings/security-keys/registration/verify", (route) =>
    route.abort("failed"),
  );
  await loginAndAuthorize(page);
  await page.getByLabel("Key Label").fill("Offline key");
  await page.getByRole("button", { name: "Add Security Key" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Reload this page to check whether the key was added",
  );
  await expect(
    page.getByRole("button", { name: "Add Security Key" }),
  ).toBeEnabled();
});

test("virtual authenticators cover enrollment, login, revocation, and backup recovery", async ({
  browser,
  page,
}, testInfo) => {
  test.setTimeout(120_000);
  const username = VIRTUAL_TEST_USERNAMES[testInfo.retry];
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("WebAuthn.enable", { enableUI: false });
  const primary = await addVirtualSecurityKey(cdp, "usb");

  await loginAndAuthorize(page, username);
  await enrollVirtualSecurityKey(page, "Primary virtual USB key");

  await page.reload({ waitUntil: "networkidle" });
  await authorizeAfterRecentStrongAuthentication(page);
  await setVirtualSecurityKeyPresence(cdp, primary, false);
  const backup = await addVirtualSecurityKey(cdp, "nfc");
  await enrollVirtualSecurityKey(page, "Backup virtual NFC key");
  await page.reload({ waitUntil: "networkidle" });
  await expect(
    page.getByText("Primary virtual USB key", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Backup virtual NFC key", { exact: true }),
  ).toBeVisible();
  await testInfo.attach("security-keys-enrolled", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });

  await page.goto("/logout", { waitUntil: "networkidle" });
  await setVirtualSecurityKeyPresence(cdp, backup, false);
  await setVirtualSecurityKeyPresence(cdp, primary, true);
  await loginWithSecurityKey(page, username);

  await page.goto("/settings/security-keys", { waitUntil: "networkidle" });
  await authorizeAfterRecentStrongAuthentication(page);
  const primaryRow = page.locator("#security-key-list li", {
    hasText: "Primary virtual USB key",
  });
  await primaryRow.getByRole("button", { name: "Remove" }).click();
  await expect(page.getByText("Security key removed")).toBeVisible();
  await expect(
    page.getByText("Primary virtual USB key", { exact: true }),
  ).toHaveCount(0);

  await page.goto("/logout", { waitUntil: "networkidle" });
  await cdp.send("WebAuthn.removeVirtualAuthenticator", {
    authenticatorId: primary,
  });
  await setVirtualSecurityKeyPresence(cdp, backup, true);
  await loginWithSecurityKey(page, username);
  await page.goto("/settings/security-keys", { waitUntil: "networkidle" });
  await expect(
    page.getByText("Backup virtual NFC key", { exact: true }),
  ).toBeVisible();
  await testInfo.attach("backup-key-recovery", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });

  await authorizeAfterRecentStrongAuthentication(page);
  await page.getByLabel(/remove every second factor/i).check();
  await page.getByRole("button", { name: "Disable All MFA" }).click();
  await expect(page.getByText("MFA disabled")).toBeVisible();
  await expect(page.locator("#security-key-empty")).toContainText(
    "No security keys are enrolled",
  );
  await testInfo.attach("validation-metadata", {
    body: Buffer.from(
      JSON.stringify(
        {
          schema_version: 1,
          build_sha: process.env.GITHUB_SHA || null,
          browser: { name: "chromium", version: browser.version() },
          rp_id: "localhost",
          origin: new URL(page.url()).origin,
          authenticators: [
            { protocol: "ctap2_1", transport: "usb", kind: "virtual" },
            { protocol: "ctap2_1", transport: "nfc", kind: "virtual" },
          ],
          passed_scenarios: [
            "primary enrollment",
            "backup enrollment",
            "primary login",
            "primary revocation",
            "backup recovery login",
            "factor cleanup",
          ],
          excluded_material: [
            "credential IDs",
            "private keys",
            "challenges",
            "cookies",
            "CSRF tokens",
          ],
        },
        null,
        2,
      ),
    ),
    contentType: "application/json",
  });
});
