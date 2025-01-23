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

  form.addEventListener("submit", async function (event) {
    event.preventDefault();

    // Loop through all encrypted fields and encrypt them
    encryptedFlag.value = "true";
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
        // If it's a UL, this means the field type is a checkbox or radio.
        // So replace the whole UL with a hidden input field
        if (field.tagName === "UL") {
          // Figure out the name of the field
          const fieldName = field.querySelector("input").name;

          field.innerHTML = ""; // Clear the contents of the <ul>
          const textarea = document.createElement("textarea");
          textarea.name = fieldName;
          textarea.disabled = true;
          textarea.value = encryptedValue;
          field.appendChild(textarea);
        } else {
          field.value = encryptedValue;
        }
      } else {
        console.error("Client-side encryption failed for field:", field.name);
        encryptedFlag.value = "false";
      }
    });

    form.submit(); // Submit the form after processing
  });
});
