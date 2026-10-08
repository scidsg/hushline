/* The first-party document restores Strict cookies for the confirmation call. */
(() => {
  const page = document.getElementById("payment-return");
  if (!page) return;
  const message = document.getElementById("payment-message");
  let attempts = 0;
  const confirm = async () => {
    attempts += 1;
    try {
      const response = await fetch(page.dataset.confirmUrl, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (response.redirected) {
        window.location.replace(response.url);
        return;
      }
      if (response.ok && (await response.json()).paid === true) {
        window.location.replace(page.dataset.setupUrl);
        return;
      }
      if (![200, 202, 503].includes(response.status))
        throw new Error("confirmation");
    } catch {
      // A temporary failure cannot authorize provisioning or lose the saved order.
    }
    if (attempts < 30) {
      window.setTimeout(confirm, 2000);
    } else {
      message.textContent =
        "Payment verification is taking longer than expected. Your order is saved. Please return to your account shortly.";
    }
  };
  confirm();
})();
