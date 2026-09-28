const { expect, test } = require("@playwright/test");

const TEST_PASSWORD = "Test-testtesttesttest-1";

async function loginAndAuthorize(page) {
  await page.addInitScript(() => {
    localStorage.setItem("hasFinishedGuidance", "true");
    sessionStorage.setItem("hushline:first-load-splash-seen", "true");
  });
  await page.goto("/login", { waitUntil: "networkidle" });
  await page.fill("#username", "jerryseinfeld");
  await page.fill("#password", TEST_PASSWORD);
  await Promise.all([
    page.waitForFunction(() => document.body?.dataset.authenticated === "true"),
    page.locator('button[type="submit"]').click(),
  ]);

  await page.goto("/settings/security-keys", { waitUntil: "networkidle" });
  await page.fill("#password", TEST_PASSWORD);
  await Promise.all([
    page.waitForURL("**/settings/security-keys"),
    page.getByRole("button", { name: "Continue" }).click(),
  ]);
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
