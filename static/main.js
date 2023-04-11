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
    const pgpOwnerInfoElement = document.getElementById('pgp-owner-info');
    pgpOwnerInfoElement.innerHTML = result.owner_info;
})();

