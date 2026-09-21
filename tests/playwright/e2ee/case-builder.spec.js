const { expect, test } = require("@playwright/test");

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
  await page.getByRole("button", { name: "Save" }).click();
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
  await expect(page.getByText("Reload sentinel note")).toBeVisible();

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

test("review markers and next-step choices remain private and user-directed", async ({
  page,
}) => {
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

  await page.locator("#case-review-stop").click();
  await expect(page.locator("#case-review-decision")).toContainText(
    "You chose not to proceed right now. Nothing has been shared.",
  );
  await expect(page.locator("#case-builder-status")).toHaveText(
    "Do not proceed right now selected. Nothing was shared.",
  );

  await page.locator("#case-review-continue").click();
  await expect(page.locator("#case-review-decision")).toHaveText(
    "You chose to continue preparing. Nothing has been shared, saved, or submitted.",
  );

  expect(editingRequests).toEqual([]);
});
