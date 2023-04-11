document.addEventListener("DOMContentLoaded", function () {
  const form = document.querySelector("form");

  form.addEventListener("submit", async function (event) {
    event.preventDefault();

    const formData = new FormData(form);
    const response = await fetch(form.action, {
      method: "POST",
      body: formData,
    });

    // Log the server's response text
    const responseText = await response.text();
    console.log("Server response text:", responseText);

    // Parse the response as JSON
    const result = JSON.parse(responseText);

    if (result.success) {
      alert("Your message has been successfully encrypted and submitted.");
      form.reset();
    } else {
      alert("An error occurred. Please try again.");
    }
  });

  const pgpInfoBtn = document.getElementById("pgp-info-btn");
  const pgpOwnerInfo = document.getElementById("pgp-owner-info");

  pgpInfoBtn.addEventListener("click", function () {
    pgpOwnerInfo.style.display = "block";
    pgpInfoBtn.disabled = true;

    const xhr = new XMLHttpRequest();
    xhr.open("GET", "/pgp_owner_info");
    xhr.onload = function () {
      if (xhr.status === 200) {
        const result = JSON.parse(xhr.responseText);
        const pgpOwnerName = document.getElementById("pgp-owner");
        const pgpKeyId = document.getElementById("pgp-key-id");
        const pgpExpires = document.getElementById("pgp-expires");

        pgpOwnerName.textContent = result.owner_info.replace('\n', '<br>');
        pgpKeyId.textContent = result.key_id;
        pgpExpires.textContent = result.expires;

        pgpOwnerInfo.style.maxHeight = pgpOwnerInfo.scrollHeight + "px";
      } else {
        console.error(xhr.statusText);
      }
      pgpInfoBtn.disabled = false;
    };
    xhr.onerror = function () {
      console.error(xhr.statusText);
      pgpInfoBtn.disabled = false;
    };
    xhr.send();
  });
});
