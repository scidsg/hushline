document.addEventListener("DOMContentLoaded", async function () {
  const pathPrefix = window.location.pathname.split("/").slice(0, -1).join("/");
  const disableAutorenewForm = document.querySelector(
    "#disable-autorenew-form",
  );
  const enableAutorenewForm = document.querySelector("#enable-autorenew-form");
  const cancelForm = document.querySelector("#cancel-form");

  if (disableAutorenewForm) {
    disableAutorenewForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      // Show confirmation dialog
      const confirmed = confirm(
        "Are you sure you want to not renew your subscription?",
      );
      if (!confirmed) return;

      // Send disable autorenew request
      const response = await fetch(`${pathPrefix}/disable-autorenew`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      });

      if (response.ok) {
        window.location.reload(); // Reload the page to reflect changes
      } else {
        const errorData = await response.json();
        console.log("Error disabling autorenew subscription:", errorData);
        alert("Error disabling autorenew. Please contact Science & Design.");
      }
    });
  }

  if (enableAutorenewForm) {
    enableAutorenewForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      // Send enable autorenew request
      const response = await fetch(`${pathPrefix}/enable-autorenew`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      });

      if (response.ok) {
        window.location.reload(); // Reload the page to reflect changes
      } else {
        const errorData = await response.json();
        console.log("Error enabling autorenew subscription:", errorData);
        alert("Error enabling autorenew. Please contact Science & Design.");
      }
    });
  }

  if (cancelForm) {
    cancelForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      // Show confirmation dialog
      const confirmed = confirm(
        "Are you sure you want to cancel your subscription?",
      );
      if (!confirmed) return;

      // Send downgrade request
      const response = await fetch(`${pathPrefix}/cancel`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      });

      if (response.ok) {
        window.location.reload(); // Reload the page to reflect changes
      } else {
        const errorData = await response.json();
        console.log("Error canceling subscription:", errorData);
        alert("Error canceling subscription. Please contact Science & Design.");
      }
    });
  }
});
