const fs = require("node:fs");
const path = require("node:path");

const { test, expect } = require("@playwright/test");

const manifest = JSON.parse(
  fs.readFileSync(path.join(__dirname, "visual-scenes.json"), "utf8"),
);

const THEMES = (manifest.themes || ["light", "dark"]).map((name) => ({
  name,
  iso: name === "dark" ? "2026-03-23T22:00:00Z" : "2026-03-23T10:00:00Z",
}));

const scenesBySlug = new Map(manifest.scenes.map((scene) => [scene.slug, scene]));
const sessions = manifest.sessions || {};
const viewportProjectNames = new Set(manifest.viewports.map((viewport) => viewport.id));
const GOTO_RETRY_ATTEMPTS = 15;
const GOTO_RETRY_DELAY_MS = 2000;

function getScene(slug) {
  const scene = scenesBySlug.get(slug);
  if (!scene) {
    throw new Error(`Unknown visual scene slug: ${slug}`);
  }
  return scene;
}

async function addStabilityHooks(page, iso) {
  await page.addInitScript(
    ({ isoString }) => {
      const fixedDate = new Date(isoString);
      const RealDate = Date;

      class MockDate extends RealDate {
        constructor(...args) {
          if (args.length === 0) {
            super(fixedDate.getTime());
            return;
          }
          super(...args);
        }

        static now() {
          return fixedDate.getTime();
        }
      }

      MockDate.parse = RealDate.parse;
      MockDate.UTC = RealDate.UTC;
      window.Date = MockDate;

      localStorage.setItem("hasFinishedGuidance", "true");
    },
    { isoString: iso },
  );
}

function isRetryableNavigationError(error) {
  if (!(error instanceof Error)) {
    return false;
  }

  return /ERR_CONNECTION_REFUSED|ERR_CONNECTION_RESET|ERR_TIMED_OUT/.test(error.message);
}

async function gotoWithRetries(page, target) {
  let lastError;

  for (let attempt = 1; attempt <= GOTO_RETRY_ATTEMPTS; attempt += 1) {
    try {
      await page.goto(target, { waitUntil: "networkidle" });
      return;
    } catch (error) {
      lastError = error;
      if (!isRetryableNavigationError(error) || attempt === GOTO_RETRY_ATTEMPTS) {
        throw error;
      }
      await page.waitForTimeout(GOTO_RETRY_DELAY_MS);
    }
  }

  throw lastError;
}

async function login(context, baseURL, sessionConfig) {
  if (!sessionConfig || !sessionConfig.username) {
    throw new Error("Authenticated visual scene is missing a valid session config.");
  }

  const password =
    (sessionConfig.passwordEnv ? process.env[sessionConfig.passwordEnv] : "") ||
    sessionConfig.password ||
    "";
  if (!password) {
    throw new Error(`No password configured for visual session ${sessionConfig.username}.`);
  }

  await context.clearCookies();
  const loginPage = await context.newPage();
  await gotoWithRetries(loginPage, baseURL);
  await loginPage.evaluate(() => {
    localStorage.setItem("hasFinishedGuidance", "true");
  });
  await gotoWithRetries(loginPage, "/login");
  await loginPage.fill("#username", sessionConfig.username);
  await loginPage.fill("#password", password);
  await Promise.all([
    loginPage.waitForLoadState("networkidle"),
    loginPage.click("button[type='submit']"),
  ]);

  if (loginPage.url().includes("/login")) {
    throw new Error(`Login failed for user ${sessionConfig.username}.`);
  }

  await loginPage.close();
}

async function submitForm(page, selector) {
  const form = page.locator(selector).first();
  const submitter = form.locator("button[type='submit'], input[type='submit']").first();
  if ((await submitter.count()) > 0 && (await submitter.isVisible())) {
    await submitter.click();
    return;
  }

  await form.evaluate((element) => {
    if (element instanceof HTMLFormElement && typeof element.requestSubmit === "function") {
      element.requestSubmit();
      return;
    }
    HTMLFormElement.prototype.submit.call(element);
  });
}

async function renderInboxState(page, messageCount) {
  await page.evaluate((targetCount) => {
    const messageList = document.querySelector(".message-list");
    if (!(messageList instanceof HTMLElement)) {
      throw new Error("Inbox message list not found.");
    }

    const badgeEls = Array.from(document.querySelectorAll(".inbox-tabs .badge"));
    const cards = Array.from(messageList.querySelectorAll("article.message"));

    if (targetCount <= 0) {
      badgeEls.forEach((badge) => {
        badge.textContent = "0";
      });
      messageList.innerHTML = `
        <div class="emptyState">
          <img class="empty" src="/static/img/empty.png" alt="Empty Inbox" />
          <h1>Nothing to see here...</h1>
          <p>No messages yet.</p>
        </div>
      `;
      return;
    }

    if (cards.length === 0) {
      throw new Error("Cannot synthesize inbox message cards from an empty inbox.");
    }

    while (cards.length > targetCount) {
      const card = cards.pop();
      card?.remove();
    }

    const templates = Array.from(messageList.querySelectorAll("article.message"));
    let cloneIndex = 0;
    while (messageList.querySelectorAll("article.message").length < targetCount) {
      const template = templates[cloneIndex % templates.length];
      const clone = template.cloneNode(true);
      if (!(clone instanceof HTMLElement)) {
        throw new Error("Inbox card clone failed.");
      }
      messageList.appendChild(clone);
      cloneIndex += 1;
    }

    if (badgeEls.length > 0) {
      badgeEls[0].textContent = String(targetCount);
    }
  }, messageCount);
}

async function stabilizeDynamicScreenshotContent(page) {
  await page.evaluate(() => {
    const captchaLabel = document.querySelector("label[for='captcha_answer']");
    if (captchaLabel instanceof HTMLElement) {
      captchaLabel.textContent = "4 + 2 =";
    }

    const captchaInput = document.querySelector("#captcha_answer");
    if (captchaInput instanceof HTMLElement) {
      captchaInput.setAttribute("aria-label", "Solve 4 + 2 = to submit your message");
    }
  });
}

async function runAction(page, action) {
  switch (action.type) {
    case "wait_for":
      await page.waitForSelector(action.selector);
      return;
    case "click": {
      let dialogPromise = null;
      if (action.acceptDialog === true) {
        dialogPromise = page.waitForEvent("dialog").then((dialog) => dialog.accept());
      }
      await page.click(action.selector);
      if (dialogPromise) {
        await dialogPromise;
      }
      if (action.waitForNetworkIdle) {
        await page.waitForLoadState("networkidle");
      }
      return;
    }
    case "click_if_exists": {
      const locator = page.locator(action.selector).first();
      if ((await locator.count()) > 0 && (await locator.isVisible())) {
        let dialogPromise = null;
        if (action.acceptDialog === true) {
          dialogPromise = page.waitForEvent("dialog").then((dialog) => dialog.accept());
        }
        await locator.click();
        if (dialogPromise) {
          await dialogPromise;
        }
        if (action.waitForNetworkIdle) {
          await page.waitForLoadState("networkidle");
        }
      }
      return;
    }
    case "fill":
      await page.fill(action.selector, action.value || "");
      return;
    case "fill_if_exists": {
      const locator = page.locator(action.selector).first();
      if ((await locator.count()) > 0 && (await locator.isVisible())) {
        await locator.fill(action.value || "");
      }
      return;
    }
    case "select_option":
      await page.selectOption(action.selector, action.value || "");
      return;
    case "sleep":
      await page.waitForTimeout(action.ms || 200);
      return;
    case "solve_math_captcha": {
      const labelText = await page.locator("label[for='captcha_answer']").textContent();
      const match = labelText?.match(/(\d+)\s*\+\s*(\d+)/);
      if (!match) {
        throw new Error(`Unable to parse CAPTCHA from label: ${labelText}`);
      }
      await page.fill("#captcha_answer", String(Number(match[1]) + Number(match[2])));
      return;
    }
    case "submit_form":
      await submitForm(page, action.selector);
      if (action.waitForNetworkIdle) {
        await page.waitForLoadState("networkidle");
      }
      return;
    case "render_inbox_state":
      await renderInboxState(page, Number(action.messageCount || 0));
      return;
    default:
      throw new Error(`Unsupported manifest action type in Playwright visual test: ${action.type}`);
  }
}

async function prepareScene(page, scene, theme, baseURL) {
  await addStabilityHooks(page, theme.iso);
  await page.emulateMedia({ colorScheme: theme.name });

  if (scene.session && scene.session !== "guest") {
    await login(page.context(), baseURL, sessions[scene.session]);
  }

  await gotoWithRetries(page, scene.path);

  if (scene.waitForSelector) {
    await page.waitForSelector(scene.waitForSelector);
  }

  for (const action of scene.actions || []) {
    await runAction(page, action);
  }

  await stabilizeDynamicScreenshotContent(page);

  await page.addStyleTag({
    content: `
      *,
      *::before,
      *::after {
        animation: none !important;
        transition: none !important;
        caret-color: transparent !important;
      }

      html {
        scroll-behavior: auto !important;
      }
    `,
  });

  await page.waitForLoadState("networkidle");
}

for (const sceneConfig of manifest.scenes) {
  const scene = getScene(sceneConfig.slug);

  for (const theme of THEMES) {
    test(`${scene.slug} (${theme.name}) matches the visual baseline`, async ({ page, baseURL }, testInfo) => {
      if (!viewportProjectNames.has(testInfo.project.name)) {
        test.skip(true, `Unexpected viewport project: ${testInfo.project.name}`);
      }

      await prepareScene(page, scene, theme, baseURL);

      await expect(page).toHaveScreenshot(`${scene.slug}-${theme.name}.png`, {
        animations: "disabled",
        caret: "hide",
        fullPage: scene.fullPage === true,
        mask: [page.locator("footer")],
      });
    });
  }
}
