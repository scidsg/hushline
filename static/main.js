document.addEventListener("DOMContentLoaded", function () {
  const form = document.querySelector("form");
  const submitButton = document.getElementById("submit-button");
  const spinner = document.querySelector(".spinner");

  form.addEventListener("submit", async function (event) {
    event.preventDefault();

    // Show the spinner and change the button text color
    spinner.style.display = 'inline-block';
    submitButton.classList.add("button-text-hidden");

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

    // Hide the spinner and restore the button text color
    spinner.style.display = 'none';
    submitButton.classList.remove("button-text-hidden");
  });
});
