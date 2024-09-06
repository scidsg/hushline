document.addEventListener("DOMContentLoaded", async function () {
  const stripeClientSecret = document.querySelector(
    "input[name='stripe_client_secret']",
  ).value;
  const stripePublishableKey = document.querySelector(
    "input[name='stripe_publishable_key']",
  ).value;
  const premiumHome = window.location.pathname
    .split("/")
    .slice(0, -1)
    .join("/");

  stripe = Stripe(stripePublishableKey);
  const elements = stripe.elements();
  const cardElement = elements.create("card");
  cardElement.mount("#card-element");

  const form = document.querySelector("#subscribe-form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const nameInput = document.getElementById("name");

    // Create payment method and confirm payment intent
    const result = await stripe.confirmCardPayment(stripeClientSecret, {
      payment_method: {
        card: cardElement,
        billing_details: {
          name: nameInput.value,
        },
      },
    });

    if (result.error) {
      alert(`Payment failed: ${result.error.message}`);
      return;
    } else {
      window.location.href = premiumHome;
    }
  });
});
