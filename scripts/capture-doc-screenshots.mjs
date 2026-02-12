#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import { chromium } from "playwright";

function getArg(name, fallback = "") {
  const idx = process.argv.indexOf(name);
  if (idx === -1 || idx + 1 >= process.argv.length) {
    return fallback;
  }
  return process.argv[idx + 1];
}

function sanitizeSlug(input) {
  return String(input)
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 120);
}

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
}

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function login(baseUrl, context, username, password) {
  const page = await context.newPage();
  // Ensure the guidance modal does not block login interactions in auth sessions.
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.evaluate(() => {
    localStorage.setItem("hasFinishedGuidance", "true");
  });
  await page.goto(`${baseUrl}/login`, { waitUntil: "networkidle" });
  await page.fill("#username", username);
  await page.fill("#password", password);
  await Promise.all([
    page.waitForLoadState("networkidle"),
    page.click("button[type='submit']"),
  ]);

  if (page.url().includes("/login")) {
    throw new Error(`Login failed for user ${username}.`);
  }

  await page.close();
}

async function runAction(page, action) {
  switch (action.type) {
    case "wait_for": {
      await page.waitForSelector(action.selector, {
        timeout: action.timeoutMs || 10000,
      });
      return;
    }
    case "click": {
      if (action.waitForSelector) {
        await page.waitForSelector(action.waitForSelector, {
          timeout: action.timeoutMs || 10000,
        });
      }
      await page.click(action.selector);
      if (action.waitForNetworkIdle) {
        await page.waitForLoadState("networkidle");
      }
      return;
    }
    case "fill": {
      await page.fill(action.selector, action.value || "");
      return;
    }
    case "set_local_storage": {
      await page.evaluate(
        ({ key, value }) => {
          localStorage.setItem(key, value);
        },
        { key: action.key, value: action.value || "" },
      );
      return;
    }
    case "remove_local_storage": {
      await page.evaluate((key) => localStorage.removeItem(key), action.key);
      return;
    }
    case "clear_local_storage": {
      await page.evaluate(() => localStorage.clear());
      return;
    }
    case "sleep": {
      await sleep(action.ms || 200);
      return;
    }
    case "solve_math_captcha": {
      const labelText = await page.$eval(
        "label[for='captcha_answer']",
        (el) => el.textContent || "",
      );
      const m = labelText.match(/(\d+)\s*\+\s*(\d+)/);
      if (!m) {
        throw new Error(
          `Unable to parse CAPTCHA expression from: ${labelText}`,
        );
      }
      const answer = String(Number(m[1]) + Number(m[2]));
      await page.fill("#captcha_answer", answer);
      return;
    }
    case "submit_form": {
      await page.$eval(action.selector, (form) => {
        HTMLFormElement.prototype.submit.call(form);
      });
      if (action.waitForNetworkIdle) {
        await page.waitForLoadState("networkidle");
      }
      return;
    }
    default:
      throw new Error(`Unknown action type: ${action.type}`);
  }
}

function makeContextOptions(viewport, jsEnabled, colorScheme) {
  const opts = {
    viewport: { width: viewport.width, height: viewport.height },
    javaScriptEnabled: jsEnabled,
    colorScheme,
  };
  if (viewport.isMobile) opts.isMobile = true;
  if (viewport.hasTouch) opts.hasTouch = true;
  if (viewport.deviceScaleFactor)
    opts.deviceScaleFactor = viewport.deviceScaleFactor;
  return opts;
}

async function main() {
  const baseUrl = getArg(
    "--base-url",
    process.env.SCREENSHOT_BASE_URL || "http://localhost:8080",
  );
  const releaseRaw = getArg(
    "--release",
    process.env.SCREENSHOT_RELEASE || new Date().toISOString().slice(0, 10),
  );
  const release = sanitizeSlug(releaseRaw);
  const manifestPath = getArg("--manifest", "docs/screenshots/scenes.json");

  const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
  const viewports = Array.isArray(manifest.viewports) ? manifest.viewports : [];
  const themes =
    Array.isArray(manifest.themes) && manifest.themes.length
      ? manifest.themes
      : ["light", "dark"];
  const defaultSettleDelayMs = Number(manifest.settleDelayMs ?? 1000);
  const sessions = manifest.sessions || {};
  const scenes = Array.isArray(manifest.scenes) ? manifest.scenes : [];

  if (!viewports.length)
    throw new Error("No viewports configured in screenshot manifest.");
  if (!scenes.length)
    throw new Error("No scenes configured in screenshot manifest.");

  const outDir = path.join("docs", "screenshots", "releases", release);
  await ensureDir(outDir);

  const browser = await chromium.launch({ headless: true });
  const contexts = new Map();
  const authenticatedContextKeys = new Set();
  const captured = [];

  function contextKey(sessionId, viewportId, theme, jsEnabled) {
    return `${sessionId}::${viewportId}::${theme}::${jsEnabled ? "js-on" : "js-off"}`;
  }

  async function getContext(sessionId, viewport, theme, jsEnabled) {
    const key = contextKey(sessionId, viewport.id, theme, jsEnabled);
    if (contexts.has(key)) {
      return contexts.get(key);
    }
    const ctx = await browser.newContext(
      makeContextOptions(viewport, jsEnabled, theme),
    );
    if (jsEnabled) {
      // Hide guidance modal by default; explicit modal scenes can clear this.
      const page = await ctx.newPage();
      await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
      await page.evaluate(() => {
        localStorage.setItem("hasFinishedGuidance", "true");
      });
      await page.close();
    }
    contexts.set(key, ctx);
    return ctx;
  }

  async function maybeAuthenticate(sessionId, viewport, theme, jsEnabled, ctx) {
    if (sessionId === "guest") return true;

    const sess = sessions[sessionId];
    if (!sess || !sess.username) {
      throw new Error(`Unknown or invalid session config: ${sessionId}`);
    }

    const envName = sess.passwordEnv || "";
    const password =
      (envName ? process.env[envName] : "") || sess.password || "";
    if (!password) {
      process.stdout.write(
        `Skipping auth scenes for session ${sessionId} (${sess.username}) because no password is configured.\n`,
      );
      return false;
    }

    const authKey = contextKey(sessionId, viewport.id, theme, jsEnabled);
    if (authenticatedContextKeys.has(authKey)) {
      return true;
    }

    await login(baseUrl, ctx, sess.username, password);
    authenticatedContextKeys.add(authKey);
    return true;
  }

  for (const scene of scenes) {
    if (!scene.slug || !scene.path || !scene.title) {
      throw new Error(`Invalid scene entry: ${JSON.stringify(scene)}`);
    }

    const sessionId = scene.session || "guest";
    const targetViewportIds =
      scene.viewports && scene.viewports.length
        ? scene.viewports
        : viewports.map((v) => v.id);

    const targetThemes =
      Array.isArray(scene.themes) && scene.themes.length ? scene.themes : themes;
    for (const viewportId of targetViewportIds) {
      const viewport = viewports.find((v) => v.id === viewportId);
      if (!viewport) {
        throw new Error(
          `Scene ${scene.slug} references unknown viewport ${viewportId}`,
        );
      }
      for (const theme of targetThemes) {
        if (theme !== "light" && theme !== "dark") {
          throw new Error(`Scene ${scene.slug} references unknown theme ${theme}`);
        }

        const jsEnabled = scene.javaScriptEnabled !== false;
        const ctx = await getContext(sessionId, viewport, theme, jsEnabled);
        const okAuth = await maybeAuthenticate(
          sessionId,
          viewport,
          theme,
          jsEnabled,
          ctx,
        );
        if (!okAuth && sessionId !== "guest") {
          continue;
        }

        const page = await ctx.newPage();

        if (Array.isArray(scene.preNavigationActions)) {
          let hasOriginLoaded = false;
          for (const action of scene.preNavigationActions) {
            if (
              action.type === "clear_local_storage" ||
              action.type === "set_local_storage" ||
              action.type === "remove_local_storage"
            ) {
              if (!hasOriginLoaded) {
                await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
                hasOriginLoaded = true;
              }
            }
            await runAction(page, action);
          }
        }

        await page.goto(`${baseUrl}${scene.path}`, { waitUntil: "networkidle" });

        if (scene.waitForSelector) {
          try {
            await page.waitForSelector(scene.waitForSelector, {
              timeout: scene.timeoutMs || 10000,
            });
          } catch (err) {
            const sessionDir = sanitizeSlug(sessionId || "guest");
            const debugDir = path.join(outDir, sessionDir);
            await ensureDir(debugDir);
            const debugFile = `${sanitizeSlug(scene.slug)}-${sanitizeSlug(viewport.id)}-${sanitizeSlug(theme)}-debug.png`;
            await page.screenshot({
              path: path.join(debugDir, debugFile),
              fullPage: false,
            });
            throw new Error(
              `Scene ${scene.slug} (${viewport.id}, ${theme}) failed waiting for selector ${scene.waitForSelector}. Debug: ${sessionDir}/${debugFile}. ${err}`,
            );
          }
        }

        if (Array.isArray(scene.actions)) {
          for (const action of scene.actions) {
            await runAction(page, action);
          }
        }

        // Let UI transitions/animations settle before we capture.
        const settleDelayMs = Number(scene.settleDelayMs ?? defaultSettleDelayMs);
        if (settleDelayMs > 0) {
          await sleep(settleDelayMs);
        }

        const files = [];
        const sessionDir = sanitizeSlug(sessionId || "guest");
        const targetDir = path.join(outDir, sessionDir);
        await ensureDir(targetDir);
        const captureModes =
          Array.isArray(scene.captureModes) && scene.captureModes.length
            ? scene.captureModes
            : ["fold", "full"];
        for (const mode of captureModes) {
          const normalizedMode = mode === "full" ? "full" : "fold";
          const fileName = `${sanitizeSlug(scene.slug)}-${sanitizeSlug(viewport.id)}-${sanitizeSlug(theme)}-${normalizedMode}.png`;
          try {
            await page.screenshot({
              path: path.join(targetDir, fileName),
              fullPage: normalizedMode === "full",
            });
            files.push({
              mode: normalizedMode,
              file: `${sessionDir}/${fileName}`,
            });
          } catch (err) {
            const fullPageOptional = scene.fullPageOptional !== false;
            if (normalizedMode === "full" && fullPageOptional) {
              process.stdout.write(
                `Skipping full-page capture for ${scene.slug} (${viewport.id}, ${theme}): ${err}\n`,
              );
              continue;
            }
            throw err;
          }
        }

        await page.close();

        captured.push({
          title: scene.title,
          slug: scene.slug,
          path: scene.path,
          session: sessionId,
          viewport: viewport.id,
          theme,
          files,
        });
      }
    }
  }

  for (const ctx of contexts.values()) {
    await ctx.close();
  }
  await browser.close();

  const now = new Date().toISOString();
  await fs.writeFile(
    path.join(outDir, "manifest.json"),
    JSON.stringify(
      {
        release,
        baseUrl,
        capturedAt: now,
        viewports,
        themes,
        sessions: Object.fromEntries(
          Object.entries(sessions).map(([k, v]) => [
            k,
            { username: v.username || "" },
          ]),
        ),
        scenes: captured,
      },
      null,
      2,
    ) + "\n",
  );

  const table = [
    "| Scene | Path | Session | Viewport | Theme | Mode | File |",
    "| --- | --- | --- | --- | --- | --- | --- |",
    ...captured.flatMap((item) =>
      item.files.map(
        (entry) =>
          `| ${item.title} | \`${item.path}\` | ${item.session} | ${item.viewport} | ${item.theme} | ${entry.mode} | ![${item.slug}-${item.viewport}-${item.theme}-${entry.mode}](./${entry.file}) |`,
      ),
    ),
  ];

  await fs.writeFile(
    path.join(outDir, "README.md"),
    [
      `# Screenshot Set: ${release}`,
      "",
      `Captured: ${now}`,
      "",
      ...table,
      "",
    ].join("\n"),
  );

  const latestDir = path.join("docs", "screenshots", "releases", "latest");
  await fs.rm(latestDir, { recursive: true, force: true });
  await fs.cp(outDir, latestDir, { recursive: true });

  const rootReadme = [
    "# Documentation Screenshots",
    "",
    "This folder stores generated screenshot sets for docs.",
    "Captures are generated from local app state using scripted scenes.",
    "Each scene captures both light and dark mode by default.",
    "Each scene captures above-the-fold and full-page by default (full-page is skipped when unsupported).",
    "Each release stores images by session under `releases/<version>/<session>/`.",
    "",
    "## Latest run",
    "",
    `- Release key: \`${release}\``,
    `- Base URL: \`${baseUrl}\``,
    `- Path: [releases/${release}/README.md](./releases/${release}/README.md)`,
    "- Latest alias: [releases/latest/README.md](./releases/latest/README.md)",
    "",
    "## Required accounts",
    "",
    "- admin (admin and org settings scenes)",
    "- artvandelay (authenticated user settings scenes)",
    "- newman (authenticated and onboarding-state settings scenes)",
    "",
    "## Regenerate",
    "",
    "```sh",
    `make docs-screenshots RELEASE=${release}`,
    "```",
    "",
  ];

  await fs.writeFile(
    path.join("docs", "screenshots", "README.md"),
    `${rootReadme.join("\n")}\n`,
  );

  process.stdout.write(
    `Captured ${captured.length} scene-viewport screenshots to ${outDir}\n`,
  );
}

main().catch((err) => {
  process.stderr.write(`${err?.stack || err}\n`);
  process.exit(1);
});
