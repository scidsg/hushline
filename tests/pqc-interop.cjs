const assert = require("node:assert/strict");
const fs = require("node:fs");
const openpgp = require("openpgp");

(async () => {
  const input = JSON.parse(fs.readFileSync(0, "utf8"));
  const publicKey = await openpgp.readKey({ armoredKey: input.public_key });
  const privateKey = await openpgp.readPrivateKey({
    armoredKey: input.private_key,
  });
  const message = await openpgp.readMessage({
    armoredMessage: input.ciphertext,
  });
  assert.equal(message.packets[0].publicKeyAlgorithm, 35);
  const decrypted = await openpgp.decrypt({
    message,
    decryptionKeys: privateKey,
  });
  const ciphertext = await openpgp.encrypt({
    message: await openpgp.createMessage({ text: input.plaintext }),
    encryptionKeys: publicKey,
  });
  const encrypted = await openpgp.readMessage({ armoredMessage: ciphertext });
  assert.equal(encrypted.packets[0].publicKeyAlgorithm, 35);
  process.stdout.write(
    JSON.stringify({ plaintext: decrypted.data, ciphertext }),
  );
})().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
