document.addEventListener("DOMContentLoaded", function() {
    const form = document.querySelector("form");

    form.addEventListener("submit", async function(event) {
        event.preventDefault();

        const formData = new FormData(form);
        const response = await fetch(form.action, {
            method: 'POST',
            body: formData
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
});

(async function () {
  const response = await fetch('/pgp_owner_info');
  const result = await response.json();
  const ownerHeading = document.getElementById('owner-heading');
  const pgpInfoElement = document.getElementById('pgp-info');
  const pgpOwnerInfoElement = document.getElementById('pgp-owner-info');
  const pgpKeyIdElement = document.getElementById('pgp-key-id');
  const pgpExpiresElement = document.getElementById('pgp-expires');

    pgpOwnerInfoElement.innerHTML = result.owner_info.replace('\n', '<br>'); // Change this line
    pgpKeyIdElement.textContent = result.key_id;
    pgpExpiresElement.textContent = result.expires;

  // Remove the 'hidden' class to show the PGP information
  // pgpInfoElement.classList.remove('hidden');
})();

$(document).ready(function() {
  $('.key-button').on('click', function() {
    $('#pgp-info p').toggleClass('show');
  });
});
