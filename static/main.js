document.addEventListener("DOMContentLoaded", function() {
    const form = document.querySelector("form");

    form.addEventListener("submit", async function(event) {
        event.preventDefault();

        const formData = new FormData(form);
        const response = await fetch(form.action, {
            method: 'POST',
            body: formData
        });
        const result = await response.json();

        if (result.success) {
            alert("Your message has been successfully encrypted and submitted.");
            form.reset();
        } else {
            alert("An error occurred. Please try again.");
        }
    });
});
