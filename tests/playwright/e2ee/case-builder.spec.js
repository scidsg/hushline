const { expect, test } = require("@playwright/test");

test("delete controls use the outlined destructive style", async ({
  page,
}, testInfo) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/case-builder", { waitUntil: "networkidle" });
  await page.locator("#case-note-draft").fill("Fictional note for visual QA");
  await page.locator("#case-note-add").click();
  const card = page.locator(".case-note-card");
  const deleteButton = card.getByRole("button", {
    name: "Delete",
    exact: true,
  });
  await expect(deleteButton).toHaveCSS(
    "background-color",
    "rgb(255, 255, 255)",
  );
  await expect(deleteButton).toHaveCSS("color", "rgb(139, 0, 0)");
  await expect(deleteButton).toHaveCSS("border-top-color", "rgb(139, 0, 0)");
  await deleteButton.hover();
  await expect(deleteButton).toHaveCSS(
    "background-color",
    "rgb(255, 255, 255)",
  );
  await deleteButton.click();
  const confirm = card.getByRole("button", { name: "Confirm delete" });
  await expect(confirm).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await expect(confirm).toHaveCSS("color", "rgb(139, 0, 0)");
  const screenshot = testInfo.outputPath("note-delete.png");
  await card.screenshot({ path: screenshot });
  await testInfo.attach("note-delete", {
    path: screenshot,
    contentType: "image/png",
  });
});

for (const width of [390, 1280]) {
  test(`case workspace choices and navigation fit at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/case-builder", { waitUntil: "networkidle" });
    await expect(page.locator("#case-evidence-safety p")).toHaveCSS(
      "font-size",
      "14px",
    );
    if (width <= 640) {
      const intro = await page.locator(".case-builder-heading p").boundingBox();
      const tabs = await page.locator(".case-builder-sections").boundingBox();
      const heading = await page.locator("#case-notes h3").boundingBox();
      expect(tabs.y - intro.y - intro.height).toBeLessThanOrEqual(8);
      expect(heading.y - tabs.y - tabs.height).toBe(28);
      expect(
        await page
          .locator(".case-builder-sections .tab")
          .first()
          .evaluate((element) => element.getBoundingClientRect().height),
      ).toBeGreaterThanOrEqual(44);
    }
    const dateInput = page.getByLabel("Date", { exact: true });
    await expect(dateInput).toHaveCSS("height", "44px");
    await expect(dateInput).toHaveCSS("width", "224px");
    await expect(page.locator(".case-builder-date svg")).toBeVisible();
    await dateInput.fill("2026-09-21");
    await expect(dateInput).toHaveValue("2026-09-21");
    await page
      .locator(".case-builder-date")
      .screenshot({ path: testInfo.outputPath(`date-${width}.png`) });
    const notesLink = page.getByRole("link", { name: "Notes", exact: true });
    const reviewLink = page.getByRole("link", { name: "Review", exact: true });
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect(notesLink).toHaveAttribute("aria-current", "location");
    await reviewLink.hover();
    await expect(reviewLink).toHaveCSS(
      "padding-left",
      width > 640 ? "0px" : "8px",
    );
    await expect(reviewLink).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    if (width > 640)
      await expect(reviewLink).toHaveCSS("text-decoration-line", "underline");
    await reviewLink.click();
    await expect(reviewLink).toHaveAttribute("aria-current", "location");
    await expect(reviewLink).toHaveCSS(
      "padding-left",
      width > 640 ? "10px" : "8px",
    );
    await expect(reviewLink).toHaveClass(/active/);
    await expect(page.locator(".case-builder-sections")).toHaveClass(
      /settings-tabs/,
    );
    await expect(reviewLink).toHaveCSS("font-family", /Atkinson Bold/);
    await expect(notesLink).not.toHaveAttribute("aria-current", "location");
    await expect(notesLink).toHaveCSS(
      "padding-left",
      width > 640 ? "0px" : "8px",
    );

    const header = await page.locator(".case-builder-header").boundingBox();
    const review = await page.locator("#case-review").boundingBox();
    expect(review.y).toBeGreaterThanOrEqual(header.y + header.height);

    for (const choice of await page.locator(".case-builder-check").all()) {
      const input = await choice.locator("input").boundingBox();
      const label = await choice.boundingBox();
      expect(input.width).toBeLessThan(32);
      expect(
        Math.abs(input.y + input.height / 2 - (label.y + label.height / 2)),
      ).toBeLessThan(1);
      await expect(choice.locator("input")).toHaveCSS("margin-right", "0px");
      await expect(choice).toHaveCSS("column-gap", "8px");
      expect(label.x).toBeGreaterThanOrEqual(0);
      expect(label.x + label.width).toBeLessThanOrEqual(width);
      // Include the anonymous text node: the original full-width input pushed it
      // outside the label even though the label's own box still fit.
      expect(
        await choice.evaluate(
          (element) => element.scrollWidth <= element.clientWidth,
        ),
      ).toBe(true);
    }

    if (width > 700) {
      await expect(
        page.getByRole("link", { name: "Notes", exact: true }),
      ).toBeInViewport();
    }
    const reviewScreenshot = testInfo.outputPath(`review-${width}.png`);
    await page.screenshot({ path: reviewScreenshot });
    await testInfo.attach(`review-${width}`, {
      path: reviewScreenshot,
      contentType: "image/png",
    });
    await page.getByRole("link", { name: "Next action", exact: true }).click();
    await page
      .getByRole("radio", { name: "Send as a tip", exact: true })
      .check();
    await expect(
      page.getByRole("radio", { name: "Send as a tip", exact: true }),
    ).toBeChecked();
    const nextActionScreenshot = testInfo.outputPath(
      `next-action-${width}.png`,
    );
    await page.screenshot({ path: nextActionScreenshot });
    await testInfo.attach(`next-action-${width}`, {
      path: nextActionScreenshot,
      contentType: "image/png",
    });
  });
}

for (const width of [390, 1280]) {
  test(`active navigation follows scrolling and record creation at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/case-builder");
    const notes = page.getByRole("link", { name: "Notes", exact: true });
    const claims = page.getByRole("link", { name: "Claims", exact: true });
    await expect(notes).toHaveAttribute("aria-current", "location");
    await page
      .locator("#case-claims")
      .evaluate((element) => element.scrollIntoView({ block: "start" }));
    await expect(claims).toHaveAttribute("aria-current", "location");
    await expect(page).toHaveURL(/\/case-builder$/);
    await page
      .locator("#case-claim-summary")
      .fill("Synthetic claim added after scrolling");
    await page.locator("#case-claim-add").click();
    await expect(claims).toHaveClass(/active/);
    await expect(claims.locator(".badge")).toHaveText("1");
    await expect(claims.locator(".badge")).toHaveCSS("opacity", "1");
    await expect(page.locator("#case-claim-summary")).toBeFocused();
    await page.getByRole("link", { name: "Timeline", exact: true }).click();
    await page
      .locator("#case-claims")
      .evaluate((element) => element.scrollIntoView({ block: "start" }));
    await expect(claims).toHaveAttribute("aria-current", "location");
    await expect(page).toHaveURL(/#case-timeline$/);
    await page.evaluate(() =>
      window.scrollTo(0, document.documentElement.scrollHeight),
    );
    const last = page.getByRole("link", { name: "Next action", exact: true });
    await expect(last).toHaveAttribute("aria-current", "location");
    if (width <= 640) {
      const ribbon = await page
        .locator(".case-builder-sections .tab-list")
        .boundingBox();
      const tab = await last.boundingBox();
      expect(tab.x).toBeGreaterThanOrEqual(ribbon.x - 1);
      expect(tab.x + tab.width).toBeLessThanOrEqual(
        ribbon.x + ribbon.width + 1,
      );
    }
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect(notes).toHaveAttribute("aria-current", "location");
    await expect(claims.locator(".badge")).toHaveCSS("opacity", "0.5");
    expect(await page.evaluate(() => window.scrollX)).toBe(0);
  });
}

test("navigation counts saved records and removes empty badges", async ({
  page,
}) => {
  await page.goto("/case-builder");
  const notes = page.getByRole("link", { name: "Notes", exact: true });
  await expect(page.locator(".case-builder-sections .badge")).toHaveCount(0);
  await page.locator("#case-note-draft").fill("Unsaved example");
  await expect(notes.locator(".badge")).toHaveCount(0);
  await page.locator("#case-note-add").click();
  await expect(notes.locator(".badge")).toHaveText("1");
  await expect(notes).toHaveAccessibleDescription("1 record");
  await page
    .locator(".case-note-card")
    .getByRole("button", { name: "Set aside", exact: true })
    .click();
  await expect(notes.locator(".badge")).toHaveText("1");
  await page.locator("#case-note-draft").fill("Second example");
  await page.locator("#case-note-add").click();
  await expect(notes.locator(".badge")).toHaveText("2");
  await page
    .locator(".case-note-card")
    .last()
    .getByRole("button", { name: "Delete", exact: true })
    .click();
  await expect(notes.locator(".badge")).toHaveText("2");
  await page
    .getByRole("button", { name: "Confirm delete", exact: true })
    .click();
  await expect(notes.locator(".badge")).toHaveText("1");
  await page
    .locator(".case-note-card")
    .getByRole("button", { name: "Delete", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm delete", exact: true })
    .click();
  await expect(notes.locator(".badge")).toHaveCount(0);
  await expect(notes).not.toHaveAttribute("aria-description");
});

test("private case workspace supports note CRUD without network or browser storage", async ({
  page,
}) => {
  await page.goto("/case-builder", { waitUntil: "networkidle" });

  const editingRequests = [];
  page.on("request", (request) => editingRequests.push(request.url()));

  const draft = page.locator("#case-note-draft");
  await expect(page.locator("#case-notes-empty")).toBeVisible();
  await page.locator("#case-note-add").click();
  await expect(page.locator(".case-note-card")).toHaveCount(0);
  await expect(page.locator("#case-builder-status")).toHaveText(
    "Enter note text before adding it.",
  );

  await draft.fill('<img src="/case-builder-leak"> private note');
  await page.locator("#case-note-add").click();
  await expect(page.locator(".case-note-text")).toHaveText(
    '<img src="/case-builder-leak"> private note',
  );
  await expect(page.locator(".case-note-card img")).toHaveCount(0);
  await expect(page.locator("#case-notes-empty")).toBeHidden();

  await page.getByRole("button", { name: "Edit" }).click();
  const editor = page.getByLabel("Edit note");
  await editor.fill("Revised private preparation note");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.locator(".case-note-text")).toHaveText(
    "Revised private preparation note",
  );

  const storageState = await page.evaluate(async () => ({
    local: window.localStorage.length,
    session: window.sessionStorage.length,
    databases:
      "databases" in indexedDB ? (await indexedDB.databases()).length : 0,
    caches: "caches" in window ? (await window.caches.keys()).length : 0,
  }));
  expect(storageState).toEqual({
    local: 0,
    session: 0,
    databases: 0,
    caches: 0,
  });

  await page.getByRole("button", { name: "Delete" }).click();
  await expect(
    page.getByText("Delete this note from the open page?"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Confirm delete" }).click();
  await expect(page.locator(".case-note-card")).toHaveCount(0);
  await expect(page.locator("#case-notes-empty")).toBeVisible();

  expect(editingRequests).toEqual([]);
});

test("reload and browser history do not restore private notes", async ({
  page,
}) => {
  await page.goto("/case-builder", { waitUntil: "networkidle" });
  await page.locator("#case-note-draft").fill("Reload sentinel note");
  await page.locator("#case-note-add").click();
  await expect(page.locator(".case-note-text")).toHaveText(
    "Reload sentinel note",
  );

  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByText("Reload sentinel note")).toHaveCount(0);
  await expect(page.locator("#case-notes-empty")).toBeVisible();

  await page.locator("#case-note-draft").fill("History sentinel note");
  await page.locator("#case-note-add").click();
  await page.locator("#case-builder-discard").click();
  await expect(page).toHaveURL(/\/directory/);

  await page.goBack({ waitUntil: "domcontentloaded" });
  await expect(page).toHaveURL(/\/case-builder$/);
  await expect(page.getByText("History sentinel note")).toHaveCount(0);
  await expect(page.locator("#case-notes-empty")).toBeVisible();

  await page.getByRole("radio", { name: "Send as a tip" }).check();
  await page.locator("#case-next-action-review").click();
  await expect(page.locator("#case-next-action-review-panel")).toContainText(
    "Send as a tip review",
  );
});

test("claims, timeline, evidence, and corroborators can be mapped safely", async ({
  page,
}) => {
  await page.goto("/case-builder", { waitUntil: "networkidle" });

  const editingRequests = [];
  page.on("request", (request) => editingRequests.push(request.url()));

  await page.locator("#case-claim-summary").fill("Payments were redirected");
  await page.locator("#case-claim-uncertain").check();
  await page.locator("#case-claim-add").click();
  await expect(page.locator(".case-claim-card")).toContainText("Core claim");
  await expect(page.locator(".case-claim-card")).toContainText(
    "Payments were redirected",
  );
  await expect(page.locator(".case-claim-card")).toContainText("Uncertain");

  await page.locator("#case-claim-summary").fill("The team changed offices");
  await page.locator("#case-claim-kind").selectOption("background");
  await page.locator("#case-claim-add").click();
  await expect(page.locator(".case-claim-card").nth(1)).toContainText(
    "Background detail",
  );

  await page.locator("#case-event-date").fill("2025-05-01");
  await page.locator("#case-event-summary").fill("Later event");
  await page.locator("#case-event-add").click();
  await page.locator("#case-event-date").fill("2025-03-01");
  await page.locator("#case-event-approximate").check();
  await page.locator("#case-event-summary").fill("Earlier event");
  await page.locator("#case-event-parties").fill("Finance team");
  await page
    .locator("#case-event-sources")
    .fill("Meeting notes already known to me");
  await page.locator("#case-event-add").click();
  await expect(page.locator(".case-event-card h4")).toHaveText([
    "About 2025-03-01",
    "2025-05-01",
  ]);
  await expect(page.locator(".case-event-card").first()).toContainText(
    "Meeting notes already known to me",
  );

  await page.locator("#case-evidence-title-input").fill("Meeting notes");
  await page
    .locator("#case-evidence-description")
    .fill("May document the payment destination");
  await page.locator("#case-evidence-missing").check();
  await page.locator("#case-evidence-uncertain").check();
  await page.locator("#case-evidence-risky").check();
  await page.locator("#case-evidence-add").click();
  await expect(page.locator(".case-evidence-card")).toContainText(
    "Meeting notes",
  );
  await expect(page.locator(".case-evidence-card")).toContainText(
    "Missing or unavailable",
  );
  await expect(page.locator(".case-evidence-card")).toContainText("Uncertain");
  await expect(page.locator(".case-evidence-card")).toContainText(
    "Risky to access — leave it alone",
  );

  await page.locator("#case-corroborator-label").fill("Former team member");
  await page
    .locator("#case-corroborator-basis")
    .fill("May have first-hand knowledge of the destination change");
  await page.locator("#case-corroborator-add").click();

  const from = page.locator("#case-connection-from");
  const to = page.locator("#case-connection-to");
  await from.selectOption({ label: "Evidence: Meeting notes" });
  await to.selectOption({ label: "Claim: Payments were redirected" });
  await page.locator("#case-connection-add").click();

  await from.selectOption({ label: "Event: 2025-03-01: Earlier event" });
  await page.locator("#case-connection-type").selectOption("context-for");
  await to.selectOption({ label: "Claim: Payments were redirected" });
  await page.locator("#case-connection-add").click();

  await from.selectOption({ label: "Corroborator: Former team member" });
  await page.locator("#case-connection-type").selectOption("corroborates");
  await to.selectOption({ label: "Claim: Payments were redirected" });
  await page.locator("#case-connection-add").click();

  await expect(page.locator(".case-connection-card")).toHaveCount(3);
  await expect(page.locator("#case-connections-list")).toContainText(
    "Evidence: Meeting notes supports Claim: Payments were redirected",
  );
  await expect(page.locator("#case-connections-list")).toContainText(
    "Corroborator: Former team member corroborates Claim: Payments were redirected",
  );

  expect(editingRequests).toEqual([]);
});

test("review markers remain private and user-directed", async ({ page }) => {
  await page.goto("/case-builder", { waitUntil: "networkidle" });

  const editingRequests = [];
  page.on("request", (request) => editingRequests.push(request.url()));

  await page.locator("#case-note-draft").fill("A detail to review");
  await page.locator("#case-note-add").click();
  const note = page.locator(".case-note-card");
  await note.getByRole("button", { name: "Mark uncertain" }).click();
  await note
    .getByRole("button", { name: "Mark sensitive or identifying" })
    .click();
  await note.getByRole("button", { name: "Set aside" }).click();
  await expect(note).toContainText("Uncertain");
  await expect(note).toContainText("Sensitive or identifying");
  await expect(note).toContainText("Set aside");

  await page.locator("#case-review-incomplete").check();
  await page.locator("#case-review-retaliation").check();
  await page.locator("#case-review-kind").selectOption("risk");
  await page
    .locator("#case-review-description")
    .fill("Consider whether this could affect another person");
  await page.locator("#case-review-uncertain").check();
  await page.locator("#case-review-identifying").check();
  await page.locator("#case-review-add").click();

  const reminder = page.locator(".case-review-card");
  await expect(reminder).toContainText("Possible consequence");
  await expect(reminder).toContainText(
    "Consider whether this could affect another person",
  );
  await expect(reminder).toContainText("Uncertain");
  await expect(reminder).toContainText("Sensitive or identifying");

  expect(editingRequests).toEqual([]);
});

test("narrative outline and high-risk next actions use a review gate", async ({
  page,
}) => {
  await page.goto("/case-builder", { waitUntil: "networkidle" });

  const editingRequests = [];
  page.on("request", (request) => editingRequests.push(request.url()));

  await page
    .locator("#case-note-draft")
    .fill("A source detail for the outline");
  await page.locator("#case-note-add").click();
  await expect(page.locator(".case-narrative-source")).toHaveCount(1);
  await expect(page.locator(".case-narrative-block")).toHaveCount(0);
  await expect(
    page
      .locator(".case-narrative-source")
      .getByRole("radio", { name: "Hold for later" }),
  ).toBeChecked();
  await page
    .locator(".case-narrative-source")
    .getByRole("radio", { name: "Exclude" })
    .check();
  await expect(page.locator(".case-narrative-block")).toHaveCount(0);

  await page.locator("#case-narrative-audience").fill("A local journalist");
  await page.locator("#case-narrative-heading").fill("Payment routing concern");
  await page.locator("#case-narrative-details-save").click();
  await page
    .locator(".case-narrative-source")
    .getByRole("radio", { name: "Include" })
    .check();
  await expect(page.locator(".case-narrative-block")).toHaveCount(1);

  const copiedPiece = page.locator(".case-narrative-block textarea");
  await copiedPiece.fill("Edited working copy for this audience");
  await copiedPiece.blur();
  await page
    .locator("#case-narrative-new-piece")
    .fill("A manually written second outline piece");
  await page.locator("#case-narrative-add-piece").click();
  await page
    .locator(".case-narrative-block")
    .nth(1)
    .getByRole("button", { name: "Move up" })
    .click();
  await expect(
    page.locator(".case-narrative-block textarea").first(),
  ).toHaveValue("A manually written second outline piece");
  await expect(page.locator(".case-note-text")).toHaveText(
    "A source detail for the outline",
  );

  await page
    .getByRole("radio", { name: "Export a password protected PDF" })
    .check();
  await page.locator("#case-next-action-review").click();
  const actionReview = page.locator("#case-next-action-review-panel");
  await expect(actionReview).toContainText(
    "Export a password protected PDF review",
  );
  await expect(actionReview).toContainText("your chosen password");
  await expect(actionReview).toContainText("A local journalist");
  await expect(actionReview).toContainText(
    "Edited working copy for this audience",
  );
  await expect(actionReview.getByRole("link")).toHaveCount(0);

  await expect(
    actionReview.getByLabel("PDF password", { exact: true }),
  ).toHaveAttribute("type", "password");
  await expect(actionReview.getByLabel("Confirm PDF password")).toHaveValue("");
  await page.getByRole("radio", { name: "Send as a tip", exact: true }).check();
  await page.locator("#case-next-action-review").click();
  await expect(actionReview).toContainText(
    "nothing is submitted until you send it",
  );
  await expect(
    actionReview.getByRole("button", { name: "Choose a recipient" }),
  ).toBeVisible();
  await page
    .getByRole("radio", { name: "Send to myself", exact: true })
    .check();
  await page.locator("#case-next-action-review").click();
  await expect(
    actionReview.getByRole("button", { name: "Open my tip page" }),
  ).toBeVisible();
  expect(editingRequests).toEqual([]);
});

test("PDF export uses the user's confirmed password and preserves the outline", async ({
  page,
}, testInfo) => {
  await page.goto("/case-builder", { waitUntil: "networkidle" });
  await page
    .locator("#case-narrative-new-piece")
    .fill("Synthetic PDF export sentinel. Résumé and café.");
  await page.locator("#case-narrative-add-piece").click();
  await page
    .getByRole("radio", {
      name: "Export a password protected PDF",
      exact: true,
    })
    .check();
  await page.locator("#case-next-action-review").click();
  const password = page.getByLabel("PDF password", { exact: true });
  const confirmation = page.getByLabel("Confirm PDF password");
  await expect(password).toHaveValue("");
  await password.fill("User-selected test passphrase 2026");
  await confirmation.fill("Mismatched test passphrase 2026");
  await page.getByRole("button", { name: "Download protected PDF" }).click();
  await expect(page.locator("#case-builder-status")).toContainText(
    "Enter matching PDF passwords",
  );
  await confirmation.fill("User-selected test passphrase 2026");
  await testInfo.attach("pdf-password-form", {
    body: await page
      .locator("#case-next-action-review-panel")
      .screenshot({ path: testInfo.outputPath("pdf-password-form.png") }),
    contentType: "image/png",
  });
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download protected PDF" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("case-outline.pdf");
  await download.saveAs(testInfo.outputPath("case-outline.pdf"));
  const { readFile } = require("node:fs/promises");
  const { PDF } = await import("@libpdf/core");
  const bytes = await readFile(testInfo.outputPath("case-outline.pdf"));
  expect(bytes.includes(Buffer.from("Synthetic PDF export sentinel"))).toBe(
    false,
  );
  for (const credentials of ["", "incorrect password"]) {
    const locked = await PDF.load(bytes, { credentials });
    expect(locked.isEncrypted).toBe(true);
    expect(locked.isAuthenticated).toBe(false);
  }
  const unlocked = await PDF.load(bytes, {
    credentials: "User-selected test passphrase 2026",
  });
  expect(unlocked.isAuthenticated).toBe(true);
  expect(unlocked.getPageCount()).toBe(1);
  await expect(password).toHaveValue("");
  await expect(confirmation).toHaveValue("");
  await expect(page.locator(".case-narrative-block textarea")).toHaveValue(
    "Synthetic PDF export sentinel. Résumé and café.",
  );
});

test("tip transfer opens a new tab and fills only the recipient's message", async ({
  page,
  context,
}) => {
  await page.goto("/case-builder", { waitUntil: "networkidle" });
  await page
    .locator("#case-note-draft")
    .fill("Private note excluded from transfer");
  await page.locator("#case-note-add").click();
  await page
    .locator("#case-narrative-new-piece")
    .fill("Reviewed tip transfer sentinel");
  await page.locator("#case-narrative-add-piece").click();
  await page.getByRole("radio", { name: "Send as a tip", exact: true }).check();
  await page.locator("#case-next-action-review").click();
  const requests = [];
  context.on("request", (request) =>
    requests.push({ url: request.url(), body: request.postData() || "" }),
  );
  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Choose a recipient" }).click();
  const recipient = await popupPromise;
  await recipient.waitForURL("**/directory");
  await recipient.goto("/to/admin", { waitUntil: "networkidle" });
  await expect(
    recipient.locator('#messageForm textarea[data-label="Message"]'),
  ).toHaveValue("Reviewed tip transfer sentinel");
  await expect(
    recipient.locator('.contextBanner[role="status"]'),
  ).toContainText("Your Case Builder outline is ready");
  expect(await recipient.evaluate(() => window.opener === null)).toBe(true);
  await expect(page).toHaveURL(/\/case-builder$/);
  await expect(page.locator(".case-note-text")).toHaveText(
    "Private note excluded from transfer",
  );
  for (const request of requests) {
    expect(request.url + request.body).not.toContain(
      "Reviewed tip transfer sentinel",
    );
    expect(request.url + request.body).not.toContain("Private note excluded");
  }
});

test("signup saves the case as an E2EE self chat without a PGP key", async ({
  page,
  context,
}, testInfo) => {
  test.setTimeout(60000);
  await context.addInitScript(() =>
    localStorage.setItem("hasFinishedGuidance", "true"),
  );
  await page.goto("/case-builder", { waitUntil: "networkidle" });
  const content =
    "Synthetic signup case: keep this content end-to-end encrypted.";
  await page.locator("#case-narrative-new-piece").fill(content);
  await page.locator("#case-narrative-add-piece").click();
  await page
    .getByRole("radio", { name: "Send to myself", exact: true })
    .check();
  await page.locator("#case-next-action-review").click();
  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Open my tip page" }).click();
  const popup = await popupPromise;
  await popup.waitForURL(/\/register\?next=/);
  const username = `case_${Date.now()}`;
  const password = "Case-test-only-very-long-password-2026";
  await popup.locator("#username").fill(username);
  await popup.locator("#password").fill(password);
  const problem = await popup
    .locator('label[for="captcha_answer"]')
    .innerText();
  const numbers = problem.match(/(\d+)\s*\+\s*(\d+)/);
  await popup
    .locator("#captcha_answer")
    .fill(String(Number(numbers[1]) + Number(numbers[2])));
  await popup.getByRole("button", { name: "Register", exact: true }).click();
  await popup.waitForURL("**/login");
  await popup.locator("#username").fill(username);
  await popup.locator("#password").fill(password);
  let savedRequest;
  const posts = [];
  popup.on("request", (request) => {
    if (request.method() === "POST") {
      posts.push(request.postData() || "");
      if (/\/conversation\/[^/]+\/messages$/.test(request.url()))
        savedRequest = request;
    }
  });
  await popup.getByRole("button", { name: "Login", exact: true }).click();
  await popup.waitForURL("**/inbox");
  expect(savedRequest).toBeTruthy();
  const payload = JSON.parse(savedRequest.postData());
  expect(payload.case_import).toBe(true);
  const copies = Object.values(payload.encrypted_copies);
  expect(copies).toHaveLength(1);
  expect(JSON.parse(copies[0])).toMatchObject({
    v: 2,
    algorithm: "ECDH-P256-AES-GCM",
  });
  for (const body of posts) expect(body).not.toContain(content);
  const savedCase = popup.locator('a[href^="/conversation/"]').first();
  await expect(popup.locator(".conversation-summary")).toContainText(
    "Saved case",
  );
  await savedCase.click();
  await expect(popup.locator(".conversation-message-body")).toHaveText(content);
  const duplicate = await popup.request.post(savedRequest.url(), {
    headers: { "X-CSRFToken": savedRequest.headers()["x-csrftoken"] },
    data: payload,
  });
  expect(duplicate.status()).toBe(200);
  await popup.reload();
  await expect(popup.locator(".conversation-message-body")).toHaveCount(1);
  await expect(popup.locator(".conversation-message-body")).toHaveText(content);
  await popup.screenshot({
    path: testInfo.outputPath("saved-case-chat.png"),
    fullPage: true,
  });
  await expect(page.locator(".case-narrative-block textarea")).toHaveValue(
    content,
  );
});

test("left navigation matches the shared Settings sidebar", async ({
  page,
  context,
}, testInfo) => {
  await context.addInitScript(() =>
    localStorage.setItem("hasFinishedGuidance", "true"),
  );
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/case-builder", { waitUntil: "networkidle" });
  const settings = await context.newPage();
  await settings.setViewportSize({ width: 1440, height: 1000 });
  await settings.goto("/login", { waitUntil: "networkidle" });
  await settings.locator("#username").fill("admin");
  await settings.locator("#password").fill("Test-testtesttesttest-1");
  await settings.getByRole("button", { name: "Login", exact: true }).click();
  await settings.waitForFunction(
    () => document.body.dataset.authenticated === "true",
  );
  await settings.goto("/settings/profile", { waitUntil: "networkidle" });
  await page.reload({ waitUntil: "networkidle" });
  const style = (locator) =>
    locator.evaluate((element) => {
      const css = getComputedStyle(element);
      return Object.fromEntries(
        [
          "paddingTop",
          "paddingRight",
          "paddingBottom",
          "paddingLeft",
          "fontFamily",
          "fontSize",
          "borderRadius",
          "boxShadow",
          "backgroundColor",
        ].map((property) => [
          property,
          // Theme color serialization differs slightly between public and account pages.
          property === "boxShadow"
            ? css[property].replace(
                /oklch\(([^)]+)\)/g,
                (_, components) =>
                  `oklch(${components
                    .split(" ")
                    .map((value, index) =>
                      Number(value).toFixed(index === 2 ? 1 : 3),
                    )
                    .join(" ")})`,
              )
            : css[property],
        ]),
      );
    });
  const actual = page.locator(".case-builder-sections .tab.active");
  const expected = settings.locator(".settings-tabs .tab.active");
  expect(await style(actual)).toEqual(await style(expected));
  expect(await style(page.locator(".case-builder-sections"))).toEqual(
    await style(settings.locator(".settings-tabs")),
  );
  await page
    .locator(".case-builder-sections")
    .screenshot({ path: testInfo.outputPath("case-builder-navigation.png") });
  await settings
    .locator(".settings-tabs")
    .screenshot({ path: testInfo.outputPath("settings-navigation.png") });
  for (const width of [320, 390, 640]) {
    await page.setViewportSize({ width, height: 900 });
    await settings.setViewportSize({ width, height: 900 });
    const contentGap = (surface, heading) =>
      surface.evaluate((selector) => {
        const tabs = document
          .querySelector(".settings-tabs")
          .getBoundingClientRect();
        const content = document
          .querySelector(selector)
          .getBoundingClientRect();
        return content.top - tabs.bottom;
      }, heading);
    expect(await contentGap(page, "#case-notes h3")).toBe(
      await contentGap(settings, ".tab-content > h3"),
    );
    await page.screenshot({
      path: testInfo.outputPath(`case-builder-mobile-${width}.png`),
    });
    await settings.screenshot({
      path: testInfo.outputPath(`settings-mobile-${width}.png`),
    });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await settings.setViewportSize({ width: 1440, height: 1000 });
  await page.locator("#case-note-draft").fill("Synthetic badge comparison");
  await page.locator("#case-note-add").click();
  await page.locator("#case-claim-summary").fill("Synthetic claim comparison");
  await page.locator("#case-claim-add").click();
  await settings.goto("/inbox", { waitUntil: "networkidle" });
  for (const selected of [true, false]) {
    const selector = selected
      ? ".tab.active .badge"
      : ".tab:not(.active) .badge";
    expect(
      await style(page.locator(`.case-builder-sections ${selector}`).first()),
    ).toEqual(await style(settings.locator(`.inbox-tabs ${selector}`).first()));
  }
  await page
    .locator(".case-builder-sections")
    .screenshot({ path: testInfo.outputPath("case-builder-count-badges.png") });
  await settings
    .locator(".inbox-tabs")
    .screenshot({ path: testInfo.outputPath("inbox-count-badges.png") });
});
