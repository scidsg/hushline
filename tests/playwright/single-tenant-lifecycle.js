/* Explicit, disposable sandbox lifecycle. Never imported by ordinary CI tests. */
const fs = require("fs");
const path = require("path");
const { chromium, expect } = require("@playwright/test");

const fixture = "6368ab5a5987358f9a9083f8ec2707b7";
const origin = "http://100.100.63.77:8777";
const privateRoot = "/Users/hushline-agent/.config/hushline/main-app-staging";
const evidenceRoot =
  "/Volumes/Storage B/hushline-dev/projects/hushline-planning/self-service-instances/main-app-staging";

async function main() {
  if (
    process.env.HUSHLINE_SINGLE_TENANT_LIFECYCLE !== fixture ||
    !["onboard", "pay", "provision", "claim-cancel", "verify-retired"].includes(
      process.argv[2],
    )
  ) {
    throw new Error("An exact, explicit sandbox lifecycle phase is required");
  }
  const phase = process.argv[2];
  const credentials = JSON.parse(
    fs.readFileSync(path.join(privateRoot, "e2e-credentials.json"), "utf8"),
  );
  const browser = await chromium.launch({
    headless: true,
    chromiumSandbox: true,
    ignoreDefaultArgs: [
      "--unsafely-disable-devtools-self-xss-warnings",
      "--enable-unsafe-swiftshader",
    ],
  });
  const statePath = path.join(privateRoot, "browser-state.json");
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    ...(phase !== "onboard" ? { storageState: statePath } : {}),
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  let step = "initialization";
  const record = (value) => {
    const destination = path.join(evidenceRoot, "browser-lifecycle.json");
    const existing = fs.existsSync(destination)
      ? JSON.parse(fs.readFileSync(destination, "utf8"))
      : { order_id: fixture, phases: [] };
    existing.phases.push({
      phase,
      ...value,
      recorded_at: new Date().toISOString(),
    });
    fs.writeFileSync(destination, JSON.stringify(existing, null, 2), {
      mode: 0o600,
    });
  };
  const save = async () => {
    await context.storageState({ path: statePath });
    fs.chmodSync(statePath, 0o600);
  };
  try {
    if (phase === "onboard") {
      step = "account-registration";
      await page.goto(origin + "/register");
      await page.locator("#username").fill(credentials.portal_username);
      await page.locator("#password").fill(credentials.portal_password);
      if (await page.locator("#invite_code").isVisible()) {
        await page.locator("#invite_code").fill(credentials.portal_invitation);
      }
      const label = await page
        .locator('label[for="captcha_answer"]')
        .innerText();
      const numbers = label.match(/(\d+)\s*\+\s*(\d+)/);
      if (!numbers)
        throw new Error("Unexpected sandbox registration challenge");
      await page
        .locator("#captcha_answer")
        .fill(String(Number(numbers[1]) + Number(numbers[2])));
      await page.getByRole("button", { name: "Register", exact: true }).click();
      await expect(page.locator("h2")).toHaveText("Login");
      step = "account-login";
      await page.locator("#username").fill(credentials.portal_username);
      await page.locator("#password").fill(credentials.portal_password);
      await page.getByRole("button", { name: "Login", exact: true }).click();
      await expect(
        page.getByRole("button", { name: "Choose Single Tenant" }),
      ).toBeVisible();
      await page
        .locator("main")
        .screenshot({ path: path.join(evidenceRoot, "plan-selection.png") });
      await page.getByRole("button", { name: "Choose Single Tenant" }).click();
      step = "annual-pricing";
      await page.locator("#quantity").fill("2");
      await expect(page.locator("#license-total")).toHaveText("$2,291.64");
      await page.getByRole("button", { name: "Continue to checkout" }).click();
      await expect(page.getByText("$2,291.64", { exact: true })).toBeVisible();
      await page
        .locator("main")
        .screenshot({ path: path.join(evidenceRoot, "annual-checkout.png") });
      await save();
      record({
        outcome: "passed",
        payment_submitted: false,
        provisioning_submitted: false,
      });
      console.log(
        "Real account creation, login, plan selection, and annual pricing passed.",
      );
    } else if (phase === "pay") {
      step = "stripe-checkout";
      await page.goto(origin + "/single-tenant");
      await page
        .getByRole("button", { name: "Pay annual total with Stripe (test)" })
        .click();
      await page.waitForURL((url) => url.hostname === "checkout.stripe.com");
      // Only public Stripe test card data; no actual card or customer information.
      await page.locator("#email").fill("test@example.com");
      await page.locator("#cardNumber").fill("4242424242424242");
      await page.locator("#cardExpiry").fill("1230");
      await page.locator("#cardCvc").fill("123");
      await page.locator("#billingName").fill("Hush Line Sandbox Fixture");
      if (await page.locator("#billingPostalCode").isVisible()) {
        await page.locator("#billingPostalCode").fill("94103");
      }
      if (await page.locator("#enableStripePass").isVisible()) {
        await page.locator("#enableStripePass").uncheck();
      }
      await page.getByTestId("hosted-payment-submit-button").click();
      await page.waitForURL((url) => url.origin === origin, { timeout: 90000 });
      await expect(
        page.getByRole("button", { name: "Provision your test instance" }),
      ).toBeVisible();
      await save();
      record({
        outcome: "passed",
        payment_submitted: true,
        provisioning_submitted: false,
      });
      console.log(
        "Stripe sandbox annual payment confirmed; no infrastructure requested yet.",
      );
    } else if (phase === "provision") {
      step = "provisioning-request";
      await page.goto(origin + "/single-tenant");
      await page
        .getByRole("button", { name: "Provision your test instance" })
        .click();
      await save();
      record({
        outcome: "submitted",
        payment_submitted: true,
        provisioning_submitted: true,
      });
      console.log(
        "Stripe sandbox payment confirmed; one provisioning request submitted.",
      );
    } else if (phase === "claim-cancel") {
      step = "explicit-dns-continue";
      await page.goto(origin + "/single-tenant");
      await expect(
        page.getByText("Step 4 of 6", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Continue to deployment checks" }),
      ).toBeVisible({ timeout: 90000 });
      await page
        .locator("main")
        .screenshot({ path: path.join(evidenceRoot, "provider-hostname.png") });
      await page
        .getByRole("button", { name: "Continue to deployment checks" })
        .click();
      await expect(
        page.getByText("Step 5 of 6", { exact: true }),
      ).toBeVisible();
      await expect(page.locator("#deployment-complete button")).toBeVisible({
        timeout: 90000,
      });
      await page.reload();
      await expect(
        page.getByText("Step 5 of 6", { exact: true }),
      ).toBeVisible();
      await page
        .locator("main")
        .screenshot({ path: path.join(evidenceRoot, "deployment-health.png") });
      await page.locator("#deployment-complete button").click();
      await expect(
        page.getByText("Step 6 of 6", { exact: true }),
      ).toBeVisible();
      await page.getByRole("button", { name: "Set up my account" }).click();
      step = "administrator-claim";
      const invitation = await page.locator("code").innerText();
      const registrationUrl = await page
        .getByRole("link", { name: "Create instance administrator" })
        .getAttribute("href");
      const instance = await context.newPage();
      await instance.goto(registrationUrl);
      await instance.locator("#username").fill(credentials.admin_username);
      await instance.locator("#password").fill(credentials.admin_password);
      await instance.locator('[name="invite_code"]').fill(invitation);
      const label = await instance
        .locator('label[for="captcha_answer"]')
        .innerText();
      const numbers = label.match(/(\d+)\s*\+\s*(\d+)/);
      if (!numbers)
        throw new Error("Unexpected sandbox administrator challenge");
      await instance
        .locator("#captcha_answer")
        .fill(String(Number(numbers[1]) + Number(numbers[2])));
      await instance
        .getByRole("button", { name: "Register", exact: true })
        .click();
      await expect(instance.locator("h2")).toHaveText("Login");
      await instance.locator("#username").fill(credentials.admin_username);
      await instance.locator("#password").fill(credentials.admin_password);
      await instance
        .getByRole("button", { name: "Login", exact: true })
        .click();
      await expect(instance.locator("body")).toHaveAttribute(
        "data-authenticated",
        "true",
      );
      await instance.close();
      step = "cancel-renewal";
      await page.goto(origin + "/single-tenant/manage");
      const deadline = await page.locator("time").getAttribute("datetime");
      await page.locator("#confirm-deletion").check();
      await page
        .getByRole("button", { name: "Cancel renewal", exact: true })
        .click();
      await expect(page.getByText(/Renewal cancelled/)).toBeVisible();
      await page.reload();
      await expect(page.getByText(/Renewal cancelled/)).toBeVisible();
      await expect(page.locator("time")).toHaveAttribute("datetime", deadline);
      await page
        .locator("main")
        .screenshot({ path: path.join(evidenceRoot, "renewal-cancelled.png") });
      await save();
      record({
        outcome: "passed",
        administrator_claimed: true,
        cancelled: true,
        period_end: deadline,
      });
      console.log(
        "Both explicit Continue gates, administrator claim/login, and persisted cancellation passed.",
      );
    } else {
      step = "retirement-verification";
      await page.goto(origin + "/single-tenant/manage");
      await expect(
        page.getByText("Your instance and stored messages have been deleted."),
      ).toBeVisible();
      await page
        .locator("main")
        .screenshot({ path: path.join(evidenceRoot, "retired.png") });
      record({ outcome: "passed", controller_retired: true });
      console.log("The same browser account reports verified retirement.");
    }
  } catch (error) {
    await save();
    record({ outcome: "failed", step, error_type: error.name });
    // Detailed browser diagnostics may contain a private Checkout or claim value.
    const diagnostic = path.join(privateRoot, "browser-failure.txt");
    fs.writeFileSync(
      diagnostic,
      String(error.stack) + "\n" + (await page.locator("body").innerText()),
      { mode: 0o600 },
    );
    console.error(
      `Sandbox browser phase failed at ${step}; private diagnostics retained.`,
    );
    process.exitCode = 1;
  } finally {
    await context.close();
    await browser.close();
  }
}
main().catch((error) => {
  console.error(`Sandbox lifecycle initialization failed (${error.name}).`);
  process.exitCode = 1;
});
