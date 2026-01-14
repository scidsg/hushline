document.addEventListener("DOMContentLoaded", function () {
  const resendForm = document.getElementById("resendMessageForm");
  if (!resendForm) {
    return;
  }

  resendForm.addEventListener("submit", function (event) {
    const confirmed = confirm(
      "Resend will send one email per field. Do you want to continue?",
    );
    if (!confirmed) {
      event.preventDefault();
    }
  });
});
