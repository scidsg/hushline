document.addEventListener("DOMContentLoaded", async function () {
  const pathPrefix = window.location.pathname.split("/").slice(0, -1).join("/");
  const downgradeForm = document.querySelector("#downgrade-form");

  // On submit
  if (downgradeForm) {
    downgradeForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      // Show confirmation dialog
      const confirmed = confirm(
        "Are you sure you want to downgrade your subscription?",
      );
      if (!confirmed) return;

      // Send downgrade request
      const response = await fetch(`${pathPrefix}/downgrade`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      });

      if (response.ok) {
        alert("Your subscription has been downgraded.");
        window.location.reload(); // Reload the page to reflect changes
      } else {
        const errorData = await response.json();
        console.log("Error downgrading subscription:", errorData);
        alert(
          "Error downgrading subscription. Please contact Science & Design.",
        );
      }
    });
  }
});
