document.addEventListener("DOMContentLoaded", async function () {
  const pathPrefix = window.location.pathname.split("/").slice(0, -1).join("/");

  // Check for payment status every 2 seconds
  setInterval(() => {
    fetch(`${pathPrefix}/status.json`)
      .then((response) => response.json())
      .then((data) => {
        if (data.tier_id === 2) {
          // Payment successful, redirect to premium home
          window.location.href = pathPrefix;
        } else {
          console.log("Payment status not yet confirmed.", data);
        }
      })
      .catch((error) => console.error("Failed to load payment status:", error));
  }, 2000);
});
