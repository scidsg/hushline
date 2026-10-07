// Demo display only. The server validates quantity and computes the checkout quote.
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("license-selection");
  if (!form) return;
  const plan = form.querySelector("#license_type");
  const quantity = form.querySelector("#quantity");
  const total = form.querySelector("#license-total");
  const breakdown = form.querySelector("#license-breakdown");
  const message = form.querySelector("#license-price-message");
  const checkout = form.querySelector("#license-checkout");
  const money = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  });
  function update() {
    const unlimited = plan.value === "unlimited";
    const valid = /^[1-9][0-9]{0,8}$/.test(quantity.value);
    quantity.disabled = unlimited;
    quantity.required = !unlimited;
    breakdown.hidden = !unlimited && !valid;
    checkout.disabled = !unlimited && !valid;
    if (!unlimited && !valid) {
      total.textContent = "—";
      message.textContent =
        "Enter a positive whole number of licenses to see your annual price.";
      return;
    }
    // Integer cents keep the preview identical to the server's Decimal quote.
    const licenses = unlimited
      ? Number(form.dataset.unlimitedAnnualLicensePrice)
      : Number(quantity.value) * 240;
    const subtotal = 128280 + Math.round(licenses * 100);
    form.querySelector("#license-cost").textContent =
      money.format(licenses) + "/year";
    for (const fee of form.querySelectorAll(".license-fee")) {
      fee.textContent = money.format(subtotal / 1000) + "/year";
    }
    total.textContent = money.format((subtotal * 13) / 1000);
    message.textContent = "The whole year is paid upfront.";
  }
  quantity.addEventListener("input", update);
  plan.addEventListener("change", update);
  update();
});
