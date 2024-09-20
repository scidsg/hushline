document.addEventListener("DOMContentLoaded", async function () {
  const pathPrefix = window.location.pathname.split("/").slice(0, -1).join("/");

  // Detect dark mode
  // https://stackoverflow.com/a/57795495
  const isDarkMode =
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  console.log("Dark mode:", isDarkMode);

  const stripeClientSecret = document.querySelector(
    "input[name='stripe_client_secret']",
  ).value;
  const stripePublishableKey = document.querySelector(
    "input[name='stripe_publishable_key']",
  ).value;

  stripe = Stripe(stripePublishableKey);
  const elements = stripe.elements({
    clientSecret: stripeClientSecret,
    appearance: {
      theme: isDarkMode ? "night" : "stripe",
    },
  });
  const paymentElement = elements.create("payment", {
    layout: "tabs",
  });
  paymentElement.mount("#payment-element");

  const form = document.querySelector("#subscribe-form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const nameInput = document.getElementById("name");

    // Confirm the payment using the Payment Element
    await stripe.confirmPayment({
      elements,
      confirmParams: {
        return_url: `${window.location.origin}${pathPrefix}/waiting`,
        payment_method_data: {
          billing_details: {
            name: nameInput.value,
          },
        },
      },
    });
  });
});
