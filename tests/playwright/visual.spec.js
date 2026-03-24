const fs = require("node:fs");
const path = require("node:path");

const { test, expect } = require("@playwright/test");

const manifest = JSON.parse(
  fs.readFileSync(path.join(__dirname, "..", "..", "docs", "screenshots", "scenes.json"), "utf8"),
);

const VISUAL_SCENE_SLUGS = [
  "guest-directory-verified",
  "guest-directory-securedrop",
  "guest-directory-globaleaks",
  "guest-profile-artvandelay",
];

const THEMES = [
  { name: "light", iso: "2026-03-23T10:00:00Z" },
  { name: "dark", iso: "2026-03-23T22:00:00Z" },
];

const scenesBySlug = new Map(manifest.scenes.map((scene) => [scene.slug, scene]));
const viewportProjectNames = new Set(manifest.viewports.map((viewport) => viewport.id));

function getScene(slug) {
  const scene = scenesBySlug.get(slug);
  if (!scene) {
    throw new Error(`Unknown visual scene slug: ${slug}`);
  }
  return scene;
}

async function addStabilityHooks(page, iso) {
  await page.addInitScript(({ isoString }) => {
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
  }, { isoString: iso });
}

async function runAction(page, action) {
  switch (action.type) {
    case "wait_for":
      await page.waitForSelector(action.selector);
      return;
    case "click":
      await page.click(action.selector);
      if (action.waitForNetworkIdle) {
        await page.waitForLoadState("networkidle");
      }
      return;
    case "click_if_exists": {
      const locator = page.locator(action.selector).first();
      if ((await locator.count()) > 0 && (await locator.isVisible())) {
        await locator.click();
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
      {
        const form = page.locator(action.selector);
        const submitter = form
          .locator("button[type='submit'], input[type='submit']")
          .first();
        if ((await submitter.count()) > 0 && (await submitter.isVisible())) {
          await submitter.click();
        } else {
          await form.evaluate((element) => {
            if (element instanceof HTMLFormElement && typeof element.requestSubmit === "function") {
              element.requestSubmit();
              return;
            }
            HTMLFormElement.prototype.submit.call(element);
          });
        }
      }
      if (action.waitForNetworkIdle) {
        await page.waitForLoadState("networkidle");
      }
      return;
    default:
      throw new Error(`Unsupported manifest action type in Playwright visual test: ${action.type}`);
  }
}

async function prepareScene(page, scene, theme) {
  await addStabilityHooks(page, theme.iso);
  await page.emulateMedia({ colorScheme: theme.name });
  await page.goto(scene.path, { waitUntil: "networkidle" });

  if (scene.waitForSelector) {
    await page.waitForSelector(scene.waitForSelector);
  }

  for (const action of scene.actions || []) {
    await runAction(page, action);
  }

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

for (const slug of VISUAL_SCENE_SLUGS) {
  const scene = getScene(slug);

  for (const theme of THEMES) {
    test(`${scene.slug} (${theme.name}) matches the visual baseline`, async ({ page }, testInfo) => {
      if (!viewportProjectNames.has(testInfo.project.name)) {
        test.skip(true, `Unexpected viewport project: ${testInfo.project.name}`);
      }

      await prepareScene(page, scene, theme);

      await expect(page).toHaveScreenshot(`${scene.slug}-${theme.name}.png`, {
        animations: "disabled",
        caret: "hide",
        mask: [page.locator("footer")],
      });
    });
  }
}
