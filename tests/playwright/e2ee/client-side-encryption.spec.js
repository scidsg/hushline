const { expect, test } = require("@playwright/test");

const PGP_ARMOR_HEADER = "-----BEGIN PGP MESSAGE-----";
const CHAT_ENVELOPE_ALGORITHM = "ECDH-P256-AES-GCM";
const TEST_PASSWORD = "Test-testtesttesttest-1";
const contactPlaintext = "P0 frontend e2ee contact sentinel";
const messagePlaintext = "P0 frontend e2ee message sentinel";

function captchaAnswer(labelText) {
  const match = labelText.match(/(\d+)\s*\+\s*(\d+)/);
  expect(
    match,
    `CAPTCHA label should be parseable: ${labelText}`,
  ).not.toBeNull();
  return String(Number(match[1]) + Number(match[2]));
}

function parseEnvelope(value) {
  expect(typeof value).toBe("string");
  const envelope = JSON.parse(value);
  expect(envelope).toMatchObject({
    v: 2,
    algorithm: CHAT_ENVELOPE_ALGORITHM,
  });
  expect(envelope.ephemeral_public_key).toBeTruthy();
  expect(envelope.iv).toBeTruthy();
  expect(envelope.ciphertext).toBeTruthy();
  expect(envelope.signature).toBeTruthy();
  expect(envelope.context).toBeTruthy();
  return envelope;
}

function expectNoPlaintext(value, plaintextValues) {
  for (const plaintext of plaintextValues) {
    expect(value).not.toContain(plaintext);
  }
}

function formValueFromPostBody(postBody, name) {
  const params = new URLSearchParams(postBody);
  if (params.has(name)) {
    return params.get(name) || "";
  }

  const marker = `name="${name}"`;
  const markerIndex = postBody.indexOf(marker);
  if (markerIndex === -1) {
    return "";
  }
  const valueStart = postBody.indexOf("\r\n\r\n", markerIndex);
  if (valueStart === -1) {
    return "";
  }
  const valueEnd = postBody.indexOf("\r\n------", valueStart + 4);
  if (valueEnd === -1) {
    return "";
  }
  return postBody.slice(valueStart + 4, valueEnd);
}

async function suppressGuidanceModal(page) {
  await page.evaluate(() => {
    localStorage.setItem("hasFinishedGuidance", "true");
    document.getElementById("guidance-modal")?.classList.remove("show");
  });
}

async function login(page, username) {
  await page.addInitScript(() => {
    localStorage.setItem("hasFinishedGuidance", "true");
  });
  await page.goto("/login", { waitUntil: "networkidle" });
  await suppressGuidanceModal(page);
  await page.fill("#username", username);
  await page.fill("#password", TEST_PASSWORD);

  await Promise.all([
    page.waitForFunction(() => document.body?.dataset.authenticated === "true"),
    page.locator('button[type="submit"]').click(),
  ]);
  await expect
    .poll(() =>
      page.evaluate(() =>
        Boolean(sessionStorage.getItem("hushline:chat-private-jwk")),
      ),
    )
    .toBe(true);
}

async function expectConversationMessage(page, plaintext) {
  await expect(
    page.locator(".conversation-message-body", { hasText: plaintext }),
  ).toBeVisible();
}

async function openUnlockedConversation(page, url, plaintext) {
  await page.goto(url, { waitUntil: "networkidle" });
  await expect(page.locator("#conversation-chat")).toBeVisible();
  await expect(page.locator("#conversation-compose-body")).toBeEnabled();
  await expectConversationMessage(page, plaintext);
}

function waitForPresenceHeartbeat(page, conversationPublicId) {
  return page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(`/conversation/${conversationPublicId}/presence`),
  );
}

async function postJsonFromPage(page, url, csrfToken, payload) {
  return page.evaluate(
    async ({ requestUrl, requestCsrfToken, requestPayload }) => {
      const response = await fetch(requestUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": requestCsrfToken,
        },
        body: JSON.stringify(requestPayload),
      });
      return {
        status: response.status,
        text: await response.text(),
      };
    },
    {
      requestUrl: url,
      requestCsrfToken: csrfToken,
      requestPayload: payload,
    },
  );
}

test("JS-enabled profile submissions encrypt fields before the POST leaves the browser", async ({
  page,
}) => {
  const consoleErrors = [];
  const pageErrors = [];
  let capturedPostBody = null;

  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    pageErrors.push(error.message);
  });
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/to/admin")) {
      capturedPostBody = request.postData() || "";
    }
  });

  await page.goto("/to/admin", { waitUntil: "networkidle" });
  await suppressGuidanceModal(page);

  await expect(page.locator("#messageForm")).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () => document.getElementById("recipientPublicKeys")?.textContent || "",
      ),
    )
    .toContain("BEGIN PGP PUBLIC KEY BLOCK");
  await expect(
    page.locator('script[src$="/static/js/client-side-encryption.js"]'),
  ).toHaveCount(1);

  await expect
    .poll(() => page.evaluate(() => window.isSecureContext))
    .toBe(true);

  await page.fill("#field_0", contactPlaintext);
  await page.fill("#field_1", messagePlaintext);
  await page.fill(
    "#captcha_answer",
    captchaAnswer(
      await page.locator('label[for="captcha_answer"]').innerText(),
    ),
  );

  await Promise.all([
    page.waitForRequest(
      (request) =>
        request.method() === "POST" && request.url().endsWith("/to/admin"),
    ),
    page.locator("#submitBtn").click(),
  ]);

  expect(pageErrors).toEqual([]);
  expect(
    consoleErrors.filter(
      (message) =>
        !message.includes("Permissions-Policy header") &&
        !message.includes("Failed to load resource"),
    ),
  ).toEqual([]);
  expect(capturedPostBody).toBeTruthy();

  const encryptedContact = formValueFromPostBody(capturedPostBody, "field_0");
  const encryptedMessage = formValueFromPostBody(capturedPostBody, "field_1");
  const encryptedEmailBody = formValueFromPostBody(
    capturedPostBody,
    "encrypted_email_body",
  );

  expect(encryptedContact).toContain(PGP_ARMOR_HEADER);
  expect(encryptedMessage).toContain(PGP_ARMOR_HEADER);
  expect(encryptedEmailBody).toContain(PGP_ARMOR_HEADER);

  expect(encryptedContact).not.toContain(contactPlaintext);
  expect(encryptedMessage).not.toContain(messagePlaintext);
  expect(encryptedEmailBody).not.toContain(contactPlaintext);
  expect(encryptedEmailBody).not.toContain(messagePlaintext);
});

test("admin broadcasts encrypt usable recipients and report malformed keys before POST", async ({
  page,
}) => {
  const broadcastPlaintext =
    "P0 frontend e2ee admin broadcast sentinel for chat launch";
  const capturedPostBodies = [];
  const dialogs = [];

  page.on("dialog", async (dialog) => {
    dialogs.push(dialog.message());
    await dialog.dismiss();
  });
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      request.url().endsWith("/settings/broadcasts")
    ) {
      capturedPostBodies.push(request.postData() || "");
    }
  });

  await login(page, "admin");
  await page.goto("/settings/broadcasts", { waitUntil: "networkidle" });
  await expect(
    page.locator("form[data-admin-broadcast-form='true']"),
  ).toBeVisible();
  await expect(
    page.locator('script[src$="/static/js/admin-broadcasts.js"]'),
  ).toHaveCount(1);
  await expect
    .poll(() => page.evaluate(() => window.isSecureContext))
    .toBe(true);

  const { failedRecipientId, mixedRecipientId } = await page.evaluate(() => {
    const script = document.getElementById("broadcastEncryptionRecipients");
    const recipients = JSON.parse(script.textContent || "[]");
    if (recipients.length < 2) {
      throw new Error(
        "Admin broadcast E2EE test requires at least two recipients.",
      );
    }
    const fallbackKey = recipients[1].public_keys.find(
      (key) => typeof key === "string" && key.trim(),
    );
    if (!fallbackKey) {
      throw new Error("Admin broadcast E2EE test requires a fallback key.");
    }
    recipients[0].public_keys = ["not armored pgp", fallbackKey];
    recipients[1].public_keys = ["not armored pgp"];
    script.textContent = JSON.stringify(recipients);
    return {
      failedRecipientId: recipients[1].user_id,
      mixedRecipientId: recipients[0].user_id,
    };
  });

  await page.fill("#broadcast_plaintext", broadcastPlaintext);
  await page.check("input[name='confirm_send']");

  await Promise.all([
    page.waitForRequest(
      (request) =>
        request.method() === "POST" &&
        request.url().endsWith("/settings/broadcasts"),
    ),
    page.locator("[name='send_broadcast']").click(),
  ]);

  await expect(page.locator("#broadcast_status")).toContainText(
    "Broadcast sent to",
  );
  expect(dialogs).toEqual([]);
  const capturedPostBody = capturedPostBodies.find((postBody) => {
    const encryptedPayloads = JSON.parse(
      formValueFromPostBody(postBody, "encrypted_payloads") || "{}",
    );
    const encryptionFailures = JSON.parse(
      formValueFromPostBody(postBody, "encryption_failures") || "[]",
    );
    return (
      Object.keys(encryptedPayloads).includes(String(mixedRecipientId)) ||
      encryptionFailures.includes(failedRecipientId)
    );
  });
  expect(capturedPostBody).toBeTruthy();
  expect(capturedPostBody).not.toContain(broadcastPlaintext);

  const encryptedPayloads = JSON.parse(
    formValueFromPostBody(capturedPostBody, "encrypted_payloads"),
  );
  const encryptionFailures = JSON.parse(
    formValueFromPostBody(capturedPostBody, "encryption_failures"),
  );

  expect(encryptionFailures).toContain(failedRecipientId);
  expect(encryptionFailures).not.toContain(mixedRecipientId);
  expect(Object.keys(encryptedPayloads)).toContain(String(mixedRecipientId));
  expect(Object.keys(encryptedPayloads)).not.toContain(
    String(failedRecipientId),
  );
  expect(Object.values(encryptedPayloads).length).toBeGreaterThan(0);
  for (const encryptedPayload of Object.values(encryptedPayloads)) {
    expect(encryptedPayload).toContain(PGP_ARMOR_HEADER);
    expectNoPlaintext(encryptedPayload, [broadcastPlaintext]);
  }
});

test("logged-in account conversation stays encrypted through browser lifecycle", async ({
  browser,
}) => {
  test.setTimeout(60000);

  const contactPlaintext = `P0 account conversation contact ${Date.now()}`;
  const sentPlaintext = `P0 account conversation initial ${Date.now()}`;
  const replyPlaintext = `P0 account conversation reply ${Date.now()}`;
  const tamperedPlaintext = `P0 malformed reply leakage ${Date.now()}`;
  const sensitiveValues = [
    contactPlaintext,
    sentPlaintext,
    replyPlaintext,
    tamperedPlaintext,
  ];

  const senderContext = await browser.newContext();
  const recipientContext = await browser.newContext();
  const senderPage = await senderContext.newPage();
  const recipientPage = await recipientContext.newPage();

  try {
    await login(senderPage, "artvandelay");

    let capturedInitialPostBody = null;
    senderPage.on("request", (request) => {
      if (
        request.method() === "POST" &&
        request.url().endsWith("/to/not_newman")
      ) {
        capturedInitialPostBody = request.postData() || "";
      }
    });

    await senderPage.goto("/to/not_newman", { waitUntil: "networkidle" });
    await suppressGuidanceModal(senderPage);
    await expect(senderPage.locator("#messageForm")).toBeVisible();
    await expect
      .poll(() =>
        senderPage.evaluate(
          () => document.getElementById("senderChatKey")?.textContent || "",
        ),
      )
      .toContain("public_signing_key");
    await expect
      .poll(() =>
        senderPage.evaluate(
          () => document.getElementById("recipientChatKey")?.textContent || "",
        ),
      )
      .toContain("public_signing_key");

    await senderPage.fill("#field_0", contactPlaintext);
    await senderPage.fill("#field_1", sentPlaintext);
    await senderPage.fill(
      "#captcha_answer",
      captchaAnswer(
        await senderPage.locator('label[for="captcha_answer"]').innerText(),
      ),
    );

    await Promise.all([
      senderPage.waitForRequest(
        (request) =>
          request.method() === "POST" &&
          request.url().endsWith("/to/not_newman"),
      ),
      senderPage.locator("#submitBtn").click(),
    ]);
    await expect(senderPage.locator("#conversation-chat")).toBeVisible();
    await expectConversationMessage(senderPage, sentPlaintext);

    expect(capturedInitialPostBody).toBeTruthy();
    expectNoPlaintext(capturedInitialPostBody, sensitiveValues);

    expect(formValueFromPostBody(capturedInitialPostBody, "field_0")).toBe(
      "Stored in encrypted conversation.",
    );
    expect(formValueFromPostBody(capturedInitialPostBody, "field_1")).toBe(
      "Stored in encrypted conversation.",
    );

    const initialCopies = JSON.parse(
      formValueFromPostBody(
        capturedInitialPostBody,
        "encrypted_conversation_copies",
      ) || "{}",
    );
    expect(Object.keys(initialCopies).sort()).toEqual(["recipient", "sender"]);
    for (const role of ["recipient", "sender"]) {
      const envelope = parseEnvelope(initialCopies[role]);
      expect(envelope.context).toMatchObject({
        purpose: "hushline.chat.initial_message",
      });
      expect(envelope.context.initial_conversation_nonce).toBeTruthy();
      expect(envelope.context.sender_key_version).toBeTruthy();
      expect(envelope.context.sender_public_key_fingerprint).toBeTruthy();
      expect(
        envelope.context.sender_public_signing_key_fingerprint,
      ).toBeTruthy();
      expect(envelope.context.recipient_key_version).toBeTruthy();
      expect(envelope.context.recipient_public_key_fingerprint).toBeTruthy();
      expectNoPlaintext(JSON.stringify(envelope), sensitiveValues);
    }

    const conversationUrl = senderPage.url();
    const conversationPublicId = await senderPage
      .locator("#conversation-chat")
      .evaluate((element) => element.dataset.conversationPublicId);
    expect(conversationUrl).toContain(`/conversation/${conversationPublicId}`);

    await login(recipientPage, "not_newman");
    const recipientPresenceResponsePromise = waitForPresenceHeartbeat(
      recipientPage,
      conversationPublicId,
    );
    await openUnlockedConversation(
      recipientPage,
      conversationUrl,
      sentPlaintext,
    );
    const recipientPresenceResponse = await recipientPresenceResponsePromise;
    const renderedPresenceCsrfToken = await recipientPage
      .locator("#conversation-chat")
      .evaluate((element) => element.dataset.csrfToken);
    expect(recipientPresenceResponse.status()).toBe(200);
    expect(recipientPresenceResponse.request().headers()["x-csrftoken"]).toBe(
      renderedPresenceCsrfToken,
    );

    let replyRequestCount = 0;
    const isReplyRequest = (request) =>
      request.method() === "POST" &&
      request.url().endsWith(`/conversation/${conversationPublicId}/messages`);
    recipientPage.on("request", (request) => {
      if (isReplyRequest(request)) {
        replyRequestCount += 1;
      }
    });
    const replyRequestPromise = recipientPage.waitForRequest(isReplyRequest);
    await recipientPage.fill("#conversation-compose-body", replyPlaintext);
    await recipientPage
      .locator("#conversation-compose-form")
      .evaluate((form) => {
        form.dispatchEvent(
          new Event("submit", { cancelable: true, bubbles: true }),
        );
        form.dispatchEvent(
          new Event("submit", { cancelable: true, bubbles: true }),
        );
      });
    const replyRequest = await replyRequestPromise;
    const replyPostBody = replyRequest.postData() || "";
    expectNoPlaintext(replyPostBody, sensitiveValues);

    const replyPayload = JSON.parse(replyPostBody);
    const rootData = await recipientPage
      .locator("#conversation-chat")
      .evaluate((element) => ({
        messageUrl: element.dataset.messageUrl,
        presenceUrl: element.dataset.presenceUrl,
        participantId: element.dataset.participantId,
      }));
    const csrfToken = await recipientPage
      .locator('#conversation-compose-form input[name="csrf_token"]')
      .inputValue();
    const participantKeys = await recipientPage.evaluate(() =>
      JSON.parse(
        document.getElementById("conversationParticipantPublicKeys")
          ?.textContent || "[]",
      ),
    );
    const participantIds = participantKeys
      .map((participant) => String(participant.participant_id))
      .sort();
    expect(Object.keys(replyPayload.encrypted_copies).sort()).toEqual(
      participantIds,
    );

    for (const [recipientParticipantId, encryptedPayload] of Object.entries(
      replyPayload.encrypted_copies,
    )) {
      const envelope = parseEnvelope(encryptedPayload);
      expect(envelope.context).toMatchObject({
        purpose: "hushline.chat.message",
        conversation_public_id: conversationPublicId,
        sender_participant_id: rootData.participantId,
        recipient_participant_id: recipientParticipantId,
      });
      expect(envelope.context.recipient_key_version).toBeTruthy();
      expect(envelope.context.recipient_public_key_fingerprint).toBeTruthy();
      expectNoPlaintext(JSON.stringify(envelope), sensitiveValues);
    }

    await expectConversationMessage(recipientPage, replyPlaintext);
    expect(replyRequestCount).toBe(1);

    const senderRefresh = senderPage.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        response.url().endsWith(`/conversation/${conversationPublicId}`),
    );
    await senderPage.reload({ waitUntil: "networkidle" });
    await senderRefresh.catch(() => undefined);
    await expectConversationMessage(senderPage, replyPlaintext);

    const malformedCopies = JSON.parse(
      JSON.stringify(replyPayload.encrypted_copies),
    );
    malformedCopies[participantIds[0]] = tamperedPlaintext;
    const malformedResponse = await postJsonFromPage(
      recipientPage,
      rootData.messageUrl,
      csrfToken,
      {
        encrypted_copies: malformedCopies,
      },
    );
    expect(malformedResponse.status).toBe(400);
    expectNoPlaintext(malformedResponse.text, sensitiveValues);

    const invalidPresenceResponse = await postJsonFromPage(
      recipientPage,
      rootData.presenceUrl,
      "invalid-presence-csrf-token",
      {},
    );
    expect(invalidPresenceResponse.status).toBe(400);
    expect(invalidPresenceResponse.text).toContain("Invalid CSRF token.");

    const tamperedCopies = JSON.parse(
      JSON.stringify(replyPayload.encrypted_copies),
    );
    const tamperedRecipientId = participantIds[0];
    const tamperedEnvelope = JSON.parse(tamperedCopies[tamperedRecipientId]);
    tamperedEnvelope.context.conversation_public_id =
      "00000000-0000-4000-8000-000000000000";
    tamperedCopies[tamperedRecipientId] = JSON.stringify(tamperedEnvelope);
    const tamperedResponse = await postJsonFromPage(
      recipientPage,
      rootData.messageUrl,
      csrfToken,
      {
        encrypted_copies: tamperedCopies,
      },
    );
    expect(tamperedResponse.status).toBe(400);
    expectNoPlaintext(tamperedResponse.text, sensitiveValues);
  } finally {
    await senderContext.close();
    await recipientContext.close();
  }
});
