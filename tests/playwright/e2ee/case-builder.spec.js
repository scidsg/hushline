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
