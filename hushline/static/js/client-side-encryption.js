function addSpacePadding(value, blockSize = 512) {
  /**
   * To hide what field is being encrypted, we need to pad the value to a fixed block size.
   * This function is used to create a padded version of the field by adding spaces to the end of the
   * value until it reaches a block size of 512 characters.
   */

  // Add padding
  const paddingLen = blockSize - (value.length % blockSize);
  const padding = " ".repeat(paddingLen);

  // Return the padded value
  return value + padding;
}

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
    return encryptedMessage;
  } catch (error) {
    console.error("Error encrypting:", error);
    return false;
  }
}

document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("messageForm");
  const encryptedFlag = document.getElementById("clientSideEncrypted");
  const publicKeyArmored = document.getElementById("publicKey")
    ? document.getElementById("publicKey").value
    : "";

  let encryptionSuccessful = true;

  form.addEventListener("submit", async function (event) {
    event.preventDefault();

    // Loop through all encrypted fields and encrypt them
    document.querySelectorAll(".encrypted-field").forEach(async (field) => {
      // Get the value
      let value = "";
      if (field.tagName === "INPUT" || field.tagName === "SELECT") {
        value = field.value;
      } else if (field.tagName === "UL") {
        const checkedValues = [];
        field
          .querySelectorAll(
            "input[type='checkbox']:checked, input[type='radio']:checked",
          )
          .forEach((input) => {
            checkedValues.push(input.value);
          });
        value = checkedValues.join(", ");
      }

      console.log("Encrypting field:", field, value);

      const paddedValue = addSpacePadding(value);
      const encryptedValue = await encryptMessage(
        publicKeyArmored,
        paddedValue,
      );
      if (encryptedValue) {
        // Replace the field with a hidden field and a disabled textarea (for show) containing the encrypted value
        let fieldName;
        if (field.tagName === "UL") {
          fieldName = field.querySelector("input").name;
        } else {
          fieldName = field.name;
        }

        // Empty out the field
        const fieldContainer = field.parentElement;
        fieldContainer.innerHTML = "";

        // Add a textarea with the encrypted value
        const hiddenInput = document.createElement("input");
        hiddenInput.type = "hidden";
        hiddenInput.name = fieldName;
        hiddenInput.value = encryptedValue;

        const textarea = document.createElement("textarea");
        textarea.disabled = true;
        textarea.value = encryptedValue;

        fieldContainer.appendChild(hiddenInput);
        fieldContainer.appendChild(textarea);
      } else {
        encryptionSuccessful = false;
        console.error("Client-side encryption failed for field:", field.name);
      }
    });

    if (encryptionSuccessful) {
      encryptedFlag.value = "true";
    }

    // Wait for the DOM to update before submitting
    setTimeout(() => {
      form.submit();
    }, 100);
  });
});
