document.addEventListener("DOMContentLoaded", function () {
  if (window.mailvelope) {
    document.querySelectorAll(".field-value.encrypted").forEach((fieldEl) => {
      if (window.mailvelope) {
        const encryptedContent =
          fieldEl.querySelector(".encrypted-content").innerText;
        const decryptionContainer = fieldEl.querySelector(
          ".mailvelope-decryption-container",
        );

        mailvelope
          .createDisplayContainer({
            id: decryptionContainer.getAttribute("id"),
            encryptedMsg: encryptedContent,
          })
          .then((displayContainer) => {
            messageElement.querySelector(".decrypted-content").style.display =
              "none";
            decryptionContainer.appendChild(displayContainer.element);
          })
          .catch((error) => {
            console.error("Decryption error:", error);
          });
      }
    });
  } else {
    console.log("Mailvelope not detected");
  }
});
