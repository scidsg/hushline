const { test, expect } = require("@playwright/test");

// Entirely fictional. This fixture is safe to publish with the PR screenshots.
const outline = [
  "SYNTHETIC QA EXAMPLE — Library invoice review",
  "Purpose and scope\nThis is a fictional quality-assurance example, not a real disclosure. I am asking a recipient to review a possible duplicate charge in an imaginary library renovation project. All names, dates, amounts, documents, and events below were invented for this demonstration. I have separated what the example describes as an observation from what remains uncertain. The private workspace also contains a reminder about identifying details; that reminder is intentionally excluded from this reviewed outline.",
  "What I observed\nOn 3 September 2026, I reviewed the ordinary monthly summary for the fictional Example Library project. Two entries appeared to describe the same reading-room installation: invoice QA-104 for 4,800 example units and invoice QA-118 for the same amount. Both referred to the same room and completion week. The similarity prompted a question; it does not establish that a duplicate payment occurred. A legitimate correction, staged payment, or separate scope of work could explain the entries. I have not described any person as responsible for wrongdoing.",
  "Sequence of events\nAround 5 September, a routine project meeting included a discussion of the installation schedule. My fictional meeting note says the work had been completed once. On 8 September, I asked whether the monthly summary would identify corrections or reversals. In this scenario, the answer was that an updated summary might follow. I do not know whether that update was issued. These dates are an aid to understanding the sequence, not proof of a payment, authorization, or intent. The first meeting date is approximate.",
  "Material already known\nThe inventory names a monthly summary and an ordinary meeting note already known to the fictional sender. No files were uploaded or attached to Case Builder. The inventory also names a restricted audit folder only to record that it has not been accessed and may be risky to seek. I have left that material alone. I am not asking anyone to obtain records without authorization, copy restricted information, or approach a source whose safety could be affected. The absence of a record should not be treated as evidence that it does not exist.",
  "Uncertainty and corroboration\nA fictional former project coordinator may remember the scope of the reading-room work, but has not been contacted for this example. Their possible knowledge is a lead, not corroboration that has already occurred. I cannot determine from the monthly summary whether the two entries produced separate payments, whether one was later reversed, or whether they cover different deliverables. The recipient should assess those possibilities independently. I have deliberately avoided adding a personal identity, contact details, access credentials, or a precise location for restricted material.",
  "Requested next step\nPlease assess whether this limited account warrants an appropriate, authorized review. If further information is needed, consider the confidentiality and safety of anyone involved before seeking it. This outline does not claim legal privilege, establish misconduct, or guarantee anonymity. It is the complete text selected for this demonstration: private notes, excluded source items, and risk reminders remain in the original workspace. The same reviewed text is used for the password protected PDF and the prefilled Hush Line message. Opening the recipient page prepares the message but does not submit it.",
];

const example = {
  note: "SYNTHETIC QA: two entries in an imaginary library summary appear similar; a correction may explain them.",
  claim: "The fictional summary may include a duplicate reading-room charge.",
  event: "Routine project meeting discussed one completed installation.",
  evidence: "Fictional monthly summary",
  evidenceDescription:
    "Two example entries, QA-104 and QA-118, each list 4,800 example units. This is an inventory description, not an attachment.",
  location:
    "An ordinary project summary already known to the fictional sender; no records sought or copied.",
  corroborator: "Fictional former project coordinator",
  basis:
    "May remember the agreed scope of work; has not been contacted and their knowledge is unconfirmed.",
  reminder:
    "Do not expose a colleague's identity or seek access to the restricted audit folder.",
};

test("PR evidence: completed workspace, protected PDF, and prefilled tip", async ({
  page,
  context,
}, testInfo) => {
  test.setTimeout(60000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await context.addInitScript(() =>
    localStorage.setItem("hasFinishedGuidance", "true"),
  );
  await page.goto("/case-builder", { waitUntil: "networkidle" });
  const fill = (id, value) => page.locator(`#${id}`).fill(value);
  const click = (id) => page.locator(`#${id}`).click();
  const check = (id) => page.locator(`#${id}`).check();
  async function capture(name, locator = page, fullPage = true) {
    const path = testInfo.outputPath(`${name}.png`);
    await locator.screenshot({
      path,
      ...(typeof locator.goto === "function" ? { fullPage } : {}),
    });
    await testInfo.attach(name, { path, contentType: "image/png" });
  }

  await fill("case-note-draft", example.note);
  await click("case-note-add");
  await fill(
    "case-note-draft",
    "PRIVATE WORKSPACE ONLY — omit identifying details from any shared outline.",
  );
  await click("case-note-add");
  await page
    .locator(".case-note-card")
    .last()
    .getByRole("button", { name: "Mark sensitive or identifying" })
    .click();
  await page
    .locator(".case-note-card")
    .last()
    .getByRole("button", { name: "Set aside" })
    .click();
  await fill("case-claim-summary", example.claim);
  await check("case-claim-uncertain");
  await click("case-claim-add");
  await fill("case-event-date", "2026-09-05");
  await check("case-event-approximate");
  await fill("case-event-summary", example.event);
  await fill(
    "case-event-parties",
    "Fictional project team; no personal identities included.",
  );
  await fill(
    "case-event-sources",
    "Fictional meeting note already known to the sender.",
  );
  await click("case-event-add");
  await fill("case-evidence-title-input", example.evidence);
  await fill("case-evidence-description", example.evidenceDescription);
  await fill("case-evidence-location", example.location);
  await check("case-evidence-uncertain");
  await click("case-evidence-add");
  await fill(
    "case-evidence-title-input",
    "Restricted audit folder — not accessed",
  );
  await fill(
    "case-evidence-description",
    "Its contents are unknown. Do not seek or copy it to complete this inventory.",
  );
  await fill("case-evidence-location", "No precise location recorded.");
  for (const id of [
    "case-evidence-missing",
    "case-evidence-uncertain",
    "case-evidence-risky",
  ])
    await check(id);
  await click("case-evidence-add");
  await fill("case-corroborator-label", example.corroborator);
  await fill("case-corroborator-basis", example.basis);
  await check("case-corroborator-uncertain");
  await click("case-corroborator-add");
  await page
    .locator("#case-connection-from")
    .selectOption({ label: `Evidence: ${example.evidence}` });
  await page
    .locator("#case-connection-to")
    .selectOption({ label: `Claim: ${example.claim}` });
  await click("case-connection-add");
  await page
    .locator("#case-connection-from")
    .selectOption({ label: `Corroborator: ${example.corroborator}` });
  await page.locator("#case-connection-type").selectOption("context-for");
  await click("case-connection-add");
  for (const id of [
    "case-review-incomplete",
    "case-review-sensitive",
    "case-review-consequences",
    "case-review-retaliation",
    "case-review-necessary",
    "case-review-set-aside",
  ])
    await check(id);
  await page.locator("#case-review-kind").selectOption("risk");
  await fill("case-review-description", example.reminder);
  await check("case-review-uncertain");
  await check("case-review-identifying");
  await click("case-review-add");
  await fill(
    "case-narrative-audience",
    "A Hush Line recipient reviewing this synthetic example",
  );
  await fill("case-narrative-heading", outline[0]);
  await click("case-narrative-details-save");
  await page
    .locator(".case-narrative-source")
    .filter({ hasText: "PRIVATE WORKSPACE ONLY" })
    .getByRole("radio", { name: "Exclude", exact: true })
    .check();
  for (const text of outline.slice(1)) {
    await fill("case-narrative-new-piece", text);
    await click("case-narrative-add-piece");
  }
  for (const id of [
    "case-narrative-include-check",
    "case-narrative-exclude-check",
    "case-narrative-hold-check",
  ])
    await check(id);

  // Leave each editor populated too, so the screenshots show every field with example values.
  // Saved records above and the reviewed narrative are the persisted-in-memory example.
  for (const [id, value] of Object.entries({
    "case-note-draft": example.note,
    "case-claim-summary": example.claim,
    "case-event-date": "2026-09-05",
    "case-event-summary": example.event,
    "case-event-parties":
      "Fictional project team; no personal identities included.",
    "case-event-sources": "Fictional meeting note already known to the sender.",
    "case-evidence-title-input": example.evidence,
    "case-evidence-description": example.evidenceDescription,
    "case-evidence-location": example.location,
    "case-corroborator-label": example.corroborator,
    "case-corroborator-basis": example.basis,
    "case-review-description": example.reminder,
    "case-narrative-new-piece": outline[outline.length - 1],
  }))
    await fill(id, value);
  await check("case-event-approximate");
  await check("case-claim-uncertain");
  await check("case-corroborator-uncertain");
  await page
    .getByRole("radio", {
      name: "Export a password protected PDF",
      exact: true,
    })
    .check();
  await click("case-next-action-review");
  await page
    .getByLabel("PDF password", { exact: true })
    .fill("Synthetic QA PDF password 2026");
  await page
    .getByLabel("Confirm PDF password")
    .fill("Synthetic QA PDF password 2026");
  await page.evaluate(() => window.scrollTo(0, 0));
  await capture("01-completed-workspace");
  for (const [index, section] of [
    "notes",
    "claims",
    "timeline",
    "evidence",
    "corroborators",
    "connections",
    "review",
    "narrative",
    "next-action",
  ].entries()) {
    await capture(
      `${String(index + 2).padStart(2, "0")}-${section}`,
      page.locator(`#case-${section}`),
    );
  }
  for (const width of [320, 390, 640, 768]) {
    await page.setViewportSize({ width, height: 900 });
    const shell = await page.locator(".case-builder-shell").boundingBox();
    const nav = await page.locator(".case-builder-sections").boundingBox();
    expect(nav.x).toBeGreaterThanOrEqual(shell.x);
    expect(nav.x + nav.width).toBeLessThanOrEqual(shell.x + shell.width + 1);
    for (const control of await page
      .locator(".case-builder-content textarea")
      .all()) {
      if (!(await control.isVisible())) continue;
      const bounds = await control.boundingBox();
      const parent = await control.locator("..").boundingBox();
      expect(bounds.x).toBeGreaterThanOrEqual(parent.x);
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(
        parent.x + parent.width + 1,
      );
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    }
    await page.getByRole("link", { name: "Next action", exact: true }).click();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBe(width);
    expect(await page.evaluate(() => window.scrollX)).toBe(0);
    await capture(`mobile-${width}-next-action`, page, false);
    await page.getByRole("link", { name: "Notes", exact: true }).click();
    await capture(`mobile-${width}-notes`, page, false);
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download protected PDF" }).click();
  const download = await downloadPromise;
  const pdfPath = testInfo.outputPath("case-outline.pdf");
  await download.saveAs(pdfPath);
  await testInfo.attach("password-protected-pdf", {
    path: pdfPath,
    contentType: "application/pdf",
  });
  const { writeFile, readFile } = require("node:fs/promises");
  await writeFile(
    testInfo.outputPath("reviewed-outline.txt"),
    outline.join("\n\n") + "\n",
  );
  const { PDF } = await import("@libpdf/core");
  const bytes = await readFile(pdfPath);
  expect(
    (await PDF.load(bytes, { credentials: "wrong password" })).isAuthenticated,
  ).toBe(false);
  expect(
    (await PDF.load(bytes, { credentials: "Synthetic QA PDF password 2026" }))
      .isAuthenticated,
  ).toBe(true);
  expect(bytes.includes(Buffer.from("PRIVATE WORKSPACE ONLY"))).toBe(false);

  await page.getByRole("radio", { name: "Send as a tip", exact: true }).check();
  await click("case-next-action-review");
  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Choose a recipient" }).click();
  const recipient = await popupPromise;
  await recipient.waitForURL("**/directory");
  let submissions = 0;
  recipient.on("request", (request) => {
    if (request.method() === "POST") submissions += 1;
  });
  await recipient.goto("/to/admin", { waitUntil: "networkidle" });
  const message = recipient.locator(
    '#messageForm textarea[data-label="Message"]',
  );
  await expect(message).toHaveValue(outline.join("\n\n"));
  await expect(message).not.toContainText("PRIVATE WORKSPACE ONLY");
  await recipient.setViewportSize({ width: 1440, height: 1000 });
  await capture("11-tip-page-with-payload", recipient);
  // Expand the native textarea with its resize handle to show more of the actual payload.
  await message.scrollIntoViewIfNeeded();
  const box = await message.boundingBox();
  await recipient.mouse.move(box.x + box.width - 3, box.y + box.height - 3);
  await recipient.mouse.down();
  await recipient.mouse.move(box.x + box.width - 3, box.y + box.height + 550, {
    steps: 12,
  });
  await recipient.mouse.up();
  await capture("12-tip-message-expanded", recipient.locator("#messageForm"));
  await message.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await capture("13-tip-message-ending", recipient.locator("#messageForm"));
  expect(submissions).toBe(0);
  await expect(page).toHaveURL(/\/case-builder(?:#case-[a-z-]+)?$/);
  await expect(page.locator(".case-narrative-block")).toHaveCount(
    outline.length - 1,
  );
});
