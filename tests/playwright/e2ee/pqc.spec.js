const { readFileSync } = require("node:fs");
const { expect, test } = require("@playwright/test");
const openpgp = require("openpgp");
const { vectors } = require("../../testdata/openpgp-pqc.json");

// Exercise the built submission handler under a restrictive CSP, without sending
// test disclosures or the RFC's public test private keys to a live service.
for (const vector of vectors) {
  test(`PQC browser submission and decryption: ${vector.id}`, async ({
    page,
  }) => {
    const violations = [];
    page.on("pageerror", (error) => violations.push(error.message));
    page.on("dialog", async (dialog) => {
      violations.push(dialog.message());
      await dialog.dismiss();
    });
    await page.route("https://pqc.test/**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith(".js")) {
        await route.fulfill({
          contentType: "application/javascript",
          body: readFileSync(`hushline/static/js/${url.pathname.slice(1)}`),
        });
      } else if (route.request().method() === "POST") {
        await route.fulfill({ body: "Submitted" });
      } else {
        await route.fulfill({
          contentType: "text/html",
          headers: {
            "Content-Security-Policy":
              "default-src 'none'; script-src 'self'; connect-src 'self'; form-action 'self'",
          },
          body: `<!doctype html><meta charset="utf-8"><script src="/diceware-words.js" defer></script>
            <script src="/client-side-encryption.js" defer></script>
            <script id="recipientPublicKeys" type="application/json">${JSON.stringify([vector.public_key])}</script>
            <script id="recipientPublicKeyEntries" type="application/json">${JSON.stringify([{ id: 1, key: vector.public_key }])}</script>
            <form id="messageForm" action="/submit" method="POST">
              <div><textarea class="form-field encrypted-field" name="message" data-label="Message">Synthetic PQC browser test: café 🔐</textarea></div>
              <input type="hidden" id="encrypted_email_body" name="encrypted_email_body">
              <input type="hidden" id="encrypted_email_fields_by_recipient" name="encrypted_email_fields_by_recipient">
              <button type="submit">Send</button>
            </form>`,
        });
      }
    });
    await page.goto("https://pqc.test/");
    const posted = page.waitForRequest((req) => req.method() === "POST");
    await page.getByRole("button", { name: "Send" }).click();
    const request = await posted;
    const fields = await new Response(request.postDataBuffer(), {
      headers: { "content-type": request.headers()["content-type"] },
    }).formData();
    expect(request.postData()).not.toContain("Synthetic PQC browser test");
    const privateKey = await openpgp.readPrivateKey({
      armoredKey: vector.private_key,
    });
    const perRecipient = JSON.parse(
      fields.get("encrypted_email_fields_by_recipient"),
    );
    for (const ciphertext of [
      fields.get("message"),
      fields.get("encrypted_email_body"),
      perRecipient[1].message,
    ]) {
      const message = await openpgp.readMessage({ armoredMessage: ciphertext });
      // Algorithm 35 proves encryption used ML-KEM-768+X25519, not a
      // traditional subkey silently selected from a mixed certificate.
      expect(message.packets[0].publicKeyAlgorithm).toBe(35);
      expect(message.packets[0].version).toBe(6);
      expect(message.packets[1].version).toBe(2);
      expect(message.packets[1].cipherAlgorithm).toBe(9);
      expect(message.packets[1].aeadAlgorithm).toBe(2);
      const { data } = await openpgp.decrypt({
        message,
        decryptionKeys: privateKey,
      });
      expect(data).toContain("Synthetic PQC browser test: café 🔐");
    }
    expect(violations).toEqual([]);
  });
}
