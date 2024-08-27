document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("messageForm");
  const messageField = document.querySelector('textarea[name="content"]');
  const contactMethodField = document.getElementById("contact_method");
  const encryptedFlag = document.getElementById("clientSideEncrypted");
  const publicKeyArmored = document.getElementById("publicKey")
    ? document.getElementById("publicKey").value
    : "";

  async function encryptMessage(publicKeyArmored, message) {
    if (!publicKeyArmored) {
      console.log(
        "Public key not provided for encryption. Encryption cannot proceed.",
      );
      return false;
    }

    try {
      const publicKey = await openpgp.readKey({ armoredKey: publicKeyArmored });
      const messageText = await openpgp.createMessage({ text: message });
      const encryptedMessage = await openpgp.encrypt({
        message: messageText,
        encryptionKeys: publicKey,
      });
      console.log("Message encrypted client-side successfully.");
      return encryptedMessage;
    } catch (error) {
      console.error("Error encrypting message:", error);
      return false;
    }
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();

    const contactMethod = contactMethodField.value.trim();
    let fullMessage = messageField.value;
    if (contactMethod) {
      fullMessage = `Contact Method: ${contactMethod}\n\n${messageField.value}`;
    }

    const encryptedMessage = await encryptMessage(
      publicKeyArmored,
      fullMessage,
    );

    if (encryptedMessage) {
      messageField.value = encryptedMessage;
      encryptedFlag.value = "true";
      contactMethodField.disabled = true; // Disable the contact method field to prevent it from being submitted
    } else {
      console.log("Client-side encryption failed, submitting plaintext.");
      encryptedFlag.value = "false";
    }

    form.submit(); // Submit the form after processing
  });
});
